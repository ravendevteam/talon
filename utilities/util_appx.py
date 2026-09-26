import ctypes
import time
import uuid
from contextlib import contextmanager

from utilities.util_logger import logger


_OUTLOOK_PREFIXES = ("microsoft.office.outlook", "microsoft.outlookforwindows")
_PACKAGE_MANAGER_IID = "9a7d4b65-5e8f-4fc7-a2e5-7f6925cb8b53"
_PACKAGE_MANAGER8_IID = "b8575330-1298-4ee2-80ee-7f659c5d2782"
_PACKAGE_MANAGER9_IID = "1aa79035-cc71-4b2e-80a6-c7041d8579a7"
_PACKAGE2_IID = "a6612fb6-7688-4ace-95fb-359538e7aa01"
_ASYNC_INFO_IID = "00000036-0000-0000-c000-000000000046"


class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check_hresult(result, operation):
    result = ctypes.c_int32(result).value
    if result < 0:
        code = result & 0xFFFFFFFF
        raise OSError(f"{operation} failed (HRESULT 0x{code:08X}): {ctypes.FormatError(result).strip()}")


class _Interface:
    def __init__(self, pointer):
        if not pointer:
            raise OSError("Windows returned a null COM interface")
        self.pointer = pointer

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.pointer:
            self.method(2, ctypes.c_uint32)(self.pointer)
            self.pointer = ctypes.c_void_p()

    def method(self, index, result_type, *argument_types):
        table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[index])

    def call(self, index, operation):
        _check_hresult(self.method(index, ctypes.c_int32)(self.pointer), operation)

    def output(self, index, result_type, operation, argument_types=(), arguments=()):
        result = result_type()
        method = self.method(index, ctypes.c_int32, *argument_types, ctypes.POINTER(result_type))
        _check_hresult(method(self.pointer, *arguments, ctypes.byref(result)), operation)
        return result

    def interface(self, index, operation, argument_types=(), arguments=()):
        return _Interface(self.output(index, ctypes.c_void_p, operation, argument_types, arguments))

    def query(self, interface_id):
        identifier = _GUID.parse(interface_id)
        return self.interface(0, f"QueryInterface({interface_id})", (ctypes.POINTER(_GUID),),
                              (ctypes.byref(identifier),))

    def string(self, runtime, index, operation):
        value = self.output(index, ctypes.c_void_p, operation)
        try:
            length = ctypes.c_uint32()
            buffer = runtime.api.WindowsGetStringRawBuffer(value, ctypes.byref(length))
            return ctypes.wstring_at(buffer, length.value) if length.value else ""
        finally:
            _check_hresult(runtime.api.WindowsDeleteString(value), "WindowsDeleteString")


class _WindowsRuntime:
    def __init__(self):
        self.api = ctypes.WinDLL("combase", use_last_error=True)
        self.api.RoInitialize.argtypes = [ctypes.c_uint32]
        self.api.RoInitialize.restype = ctypes.c_int32
        self.api.RoUninitialize.argtypes = []
        self.api.RoUninitialize.restype = None
        self.api.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                                 ctypes.POINTER(ctypes.c_void_p)]
        self.api.WindowsCreateString.restype = ctypes.c_int32
        self.api.WindowsDeleteString.argtypes = [ctypes.c_void_p]
        self.api.WindowsDeleteString.restype = ctypes.c_int32
        self.api.WindowsGetStringRawBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.api.WindowsGetStringRawBuffer.restype = ctypes.c_void_p
        self.api.RoActivateInstance.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.api.RoActivateInstance.restype = ctypes.c_int32
        self.initialized = False

    def __enter__(self):
        result = self.api.RoInitialize(1)
        if result & 0xFFFFFFFF != 0x80010106:
            _check_hresult(result, "RoInitialize")
            self.initialized = True
        return self

    def __exit__(self, *_):
        if self.initialized:
            self.api.RoUninitialize()
            self.initialized = False

    @contextmanager
    def string(self, value):
        handle = ctypes.c_void_p()
        length = len(value.encode("utf-16-le")) // 2
        _check_hresult(self.api.WindowsCreateString(value, length, ctypes.byref(handle)),
                       "WindowsCreateString")
        try:
            yield handle
        finally:
            _check_hresult(self.api.WindowsDeleteString(handle), "WindowsDeleteString")

    def package_manager(self):
        with self.string("Windows.Management.Deployment.PackageManager") as class_name:
            pointer = ctypes.c_void_p()
            _check_hresult(self.api.RoActivateInstance(class_name, ctypes.byref(pointer)),
                           "RoActivateInstance(PackageManager)")
        with _Interface(pointer) as instance:
            return instance.query(_PACKAGE_MANAGER_IID)


def _record_failure(failures, operation, error):
    logger.exception("%s failed", operation)
    failures.append(f"{operation}: {error}")


def _outlook_identity(package, runtime, family_name):
    with package.interface(6, "Package.Id") as identity:
        name = identity.string(runtime, 6, "PackageId.Name")
        logger.debug("Inspecting %s Outlook candidate: %s", "provisioned" if family_name else "installed", name)
        if not name.casefold().startswith(_OUTLOOK_PREFIXES):
            return None
        if not family_name:
            with package.query(_PACKAGE2_IID) as details:
                is_resource = details.output(10, ctypes.c_ubyte, "Package.IsResourcePackage").value
                is_bundle = details.output(11, ctypes.c_ubyte, "Package.IsBundle").value
                if is_resource or is_bundle:
                    logger.debug("Skipping Outlook resource or bundle entry: %s", name)
                    return None
        return identity.string(runtime, 13 if family_name else 12,
                               "PackageId.FamilyName" if family_name else "PackageId.FullName")


def _installed_outlook_packages(manager, runtime, failures):
    packages = []
    with manager.interface(12, "PackageManager.FindPackagesForUser", (ctypes.c_void_p,), (None,)) as collection:
        with collection.interface(6, "Packages.First") as iterator:
            has_current = iterator.output(7, ctypes.c_ubyte, "Packages.HasCurrent").value
            index = 0
            while has_current:
                try:
                    with iterator.interface(6, "Packages.Current") as package:
                        name = _outlook_identity(package, runtime, False)
                        if name:
                            packages.append(name)
                except Exception as error:
                    _record_failure(failures, f"Inspect installed package {index}", error)
                has_current = iterator.output(8, ctypes.c_ubyte, "Packages.MoveNext").value
                index += 1
    return packages


def _provisioned_outlook_packages(manager, runtime, failures):
    packages = set()
    with manager.query(_PACKAGE_MANAGER9_IID) as provisioning:
        with provisioning.interface(6, "PackageManager.FindProvisionedPackages") as collection:
            count = collection.output(7, ctypes.c_uint32, "ProvisionedPackages.Size").value
            for index in range(count):
                try:
                    with collection.interface(6, "ProvisionedPackages.GetAt", (ctypes.c_uint32,), (index,)) as package:
                        name = _outlook_identity(package, runtime, True)
                        if name:
                            packages.add(name)
                except Exception as error:
                    _record_failure(failures, f"Inspect provisioned package {index}", error)
    return sorted(packages)


def _wait_for_deployment(operation, runtime, label):
    with operation.query(_ASYNC_INFO_IID) as info:
        status = info.output(7, ctypes.c_int32, "Deployment.Status").value
        next_log = time.monotonic() + 30
        while status == 0:
            time.sleep(0.1)
            status = info.output(7, ctypes.c_int32, "Deployment.Status").value
            if time.monotonic() >= next_log:
                logger.info("Waiting for %s", label)
                next_log = time.monotonic() + 30
        try:
            error_code = info.output(8, ctypes.c_int32, "Deployment.ErrorCode").value
            if status != 1 or error_code < 0:
                logger.error("%s ended with status %s and HRESULT 0x%08X", label, status,
                             error_code & 0xFFFFFFFF)
            with operation.interface(10, f"{label}.GetResults") as result:
                error_text = result.string(runtime, 6, "DeploymentResult.ErrorText")
                activity_id = result.output(7, _GUID, "DeploymentResult.ActivityId")
                activity = str(uuid.UUID(bytes_le=bytes(activity_id)))
                extended_error = result.output(8, ctypes.c_int32, "DeploymentResult.ExtendedErrorCode").value
                logger.info("%s deployment activity: %s", label, activity)
                if error_text:
                    logger.log(40 if status != 1 or extended_error < 0 else 20,
                               "%s: %s", label, error_text)
                _check_hresult(extended_error, f"{label}: {error_text}")
            _check_hresult(error_code, label)
            if status != 1:
                raise OSError(f"{label} did not complete successfully (status {status})")
        finally:
            try:
                info.call(10, "Deployment.Close")
            except Exception:
                logger.exception("Failed to close completed deployment for %s", label)
                raise


def _remove_installed_outlook(manager, runtime, failures):
    packages = _installed_outlook_packages(manager, runtime, failures)
    if not packages:
        logger.info("No Outlook AppX packages are installed for the current user")
    for name in packages:
        label = f"Remove installed Outlook package {name}"
        try:
            logger.info("%s", label)
            with runtime.string(name) as package_name:
                with manager.interface(8, "PackageManager.RemovePackageAsync", (ctypes.c_void_p,),
                                       (package_name,)) as operation:
                    _wait_for_deployment(operation, runtime, label)
            logger.info("Removed installed Outlook package %s", name)
        except Exception as error:
            _record_failure(failures, label, error)


def _remove_provisioned_outlook(manager, runtime, failures):
    packages = _provisioned_outlook_packages(manager, runtime, failures)
    if not packages:
        logger.info("No Outlook AppX packages are provisioned for new users")
        return
    with manager.query(_PACKAGE_MANAGER8_IID) as provisioning:
        for name in packages:
            label = f"Deprovision Outlook package {name}"
            try:
                logger.info("%s", label)
                with runtime.string(name) as package_name:
                    with provisioning.interface(6, "PackageManager.DeprovisionPackageForAllUsersAsync",
                                                (ctypes.c_void_p,), (package_name,)) as operation:
                        _wait_for_deployment(operation, runtime, label)
                logger.info("Deprovisioned Outlook package %s", name)
            except Exception as error:
                _record_failure(failures, label, error)


def remove_outlook_packages():
    failures = []
    try:
        with _WindowsRuntime() as runtime:
            with runtime.package_manager() as manager:
                for label, remove in (("Remove current-user Outlook packages", _remove_installed_outlook),
                                      ("Deprovision Outlook packages", _remove_provisioned_outlook)):
                    try:
                        remove(manager, runtime, failures)
                    except Exception as error:
                        _record_failure(failures, label, error)
    except Exception as error:
        _record_failure(failures, "Initialize native Outlook package removal", error)
    return failures
