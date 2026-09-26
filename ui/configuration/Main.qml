import QtQuick 2.15
import QtQuick.Window 2.15

Window {
	id: window
	visible: true
	width: 1100
	height: 660
	color: "transparent"
	title: "RAVEN Talon"
	flags: Qt.Window | Qt.FramelessWindowHint
	visibility: Window.Windowed

	property int titleBarHeight: 38
	property int titleFontSize: 14
	property color borderColor: "#2A2A2A"
	property int resizeMargin: 6
	property int currentPage: 0
	property bool internetAvailable: true

	function refreshPlanViews() {
		if (typeof readyPage !== "undefined") {
			readyPage.refreshAdvancedArgs()
			readyPage.refreshConfigItems()
			readyPage.refreshPresetOptions()
		}
	}

	Component.onCompleted: {
		if (window.visibility !== Window.Maximized) {
			Qt.callLater(function() {
				window.x = Math.round((Screen.width - window.width) / 2)
				window.y = Math.round((Screen.height - window.height) / 2)
			})
		}
	}

	FontLoader { id: sarpanchFont; source: "../../media/sarpanch_bold.ttf" }
	FontLoader { id: interFont; source: "../../media/inter_regular.ttf" }
	FontLoader { id: cascadiaMonoFont; source: "../../media/cascadia_mono.ttf" }

	WindowChrome {
		anchors.fill: parent
		appWindow: window
		titleBarHeight: window.titleBarHeight
		titleFontSize: window.titleFontSize
		resizeMargin: window.resizeMargin
		borderColor: window.borderColor

		I18nBinding {
			id: localizer
		}

		LoadingPage {
			anchors.fill: parent
			visible: window.currentPage === 0
		}

		LanguageSelector {
			id: languageSelector
			anchors.left: parent.left
			anchors.leftMargin: 14
			anchors.top: parent.top
			anchors.topMargin: 14
			languages: i18n.availableLanguages()
			currentLanguage: i18n.currentLanguage
			interFontFamily: interFont.name
			visible: window.currentPage === 1 && (readyPage.showBrowserSelection || readyPage.showDebloatSummary || readyPage.showAdvancedPage)
			onLanguageRequested: function(code) {
				i18n.setLanguage(code)
			}
		}

		MouseArea {
			anchors.fill: parent
			visible: languageSelector.dropdownOpen
			z: languageSelector.z - 1
			hoverEnabled: true
			onClicked: languageSelector.closeDropdown()
		}

		Item {
			id: readyPage
			anchors.fill: parent
			visible: window.currentPage === 1

			property bool showBrowserSelection: false
			property bool showDebloatSummary: false
			property bool showAdvancedPage: false
			property bool transitionToSummaryInProgress: false
			property string selectedBrowser: ""
			property string selectedBrowserName: ""
			property var configItems: []
			property var advancedArgs: []
			property var browsers: []
			property var presetOptions: []
			property string selectedPresetKey: ""

			function refreshConfigItems() {
				configItems = bridge.getInstallPlanItems()
			}

			function refreshAdvancedArgs() {
				advancedArgs = bridge.getAdvancedArgs()
			}

			function refreshPresetOptions() {
				presetOptions = bridge.getPresetOptions()
				selectedPresetKey = bridge.getSelectedPresetKey()
			}

			function refreshLocalizedModels() {
				browsers = bridge.getBrowserOptions()
				refreshConfigItems()
				refreshAdvancedArgs()
				refreshPresetOptions()
			}

			function openWin11ArgsDialog() {
				advancedDialog.openDialog(localizer.text("configuration.dialogs.win11_args_title"), bridge.getWin11DebloatArgsText(), "win11debloat")
			}

			function openRegistryChangesDialog() {
				advancedDialog.openDialog(localizer.text("configuration.dialogs.registry_changes_title"), bridge.getRegistryChangesText(), "registry-changes")
			}

			function openProgramPackagesDialog() {
				advancedDialog.openDialog(localizer.text("configuration.dialogs.program_packages_title"), bridge.getChocolateyPackagesText(), "program-packages", "configuration.dialogs.program_packages_help")
			}

			function openGroupPolicyChangesDialog() {
				if (bridge.isGroupPolicyAvailable())
					advancedDialog.openDialog(localizer.text("configuration.dialogs.group_policy_changes_title"), bridge.getGroupPolicyChangesText(), "group-policy", "configuration.dialogs.group_policy_changes_help")
			}

			onVisibleChanged: {
				if (visible) {
					showBrowserSelection = false
					showDebloatSummary = false
					showAdvancedPage = false
					transitionToSummaryInProgress = false
					selectedBrowser = ""
					selectedBrowserName = ""
					refreshLocalizedModels()
					introTimer.restart()
				}
			}

			Connections {
				target: i18n
				function onLanguageChanged() {
					readyPage.refreshLocalizedModels()
					if (advancedDialog.visible) {
						if (advancedDialog.mode === "win11debloat")
							advancedDialog.titleText = localizer.text("configuration.dialogs.win11_args_title")
						else if (advancedDialog.mode === "registry-changes")
							advancedDialog.titleText = localizer.text("configuration.dialogs.registry_changes_title")
						else if (advancedDialog.mode === "program-packages")
							advancedDialog.titleText = localizer.text("configuration.dialogs.program_packages_title")
						else if (advancedDialog.mode === "group-policy")
							advancedDialog.titleText = localizer.text("configuration.dialogs.group_policy_changes_title")
					}
				}
			}

			Timer {
				id: introTimer
				interval: 2000
				repeat: false
				onTriggered: {
					if (window.internetAvailable)
						readyPage.showBrowserSelection = true
					else
						readyPage.showDebloatSummary = true
				}
			}

			Timer {
				id: browserToSummaryTimer
				interval: 500
				repeat: false
				onTriggered: {
					readyPage.showDebloatSummary = true
					readyPage.transitionToSummaryInProgress = false
				}
			}

			Row {
				id: logoRow
				anchors.horizontalCenter: parent.horizontalCenter
				anchors.verticalCenter: parent.verticalCenter
				spacing: 10
				height: 34
				opacity: (readyPage.showBrowserSelection || readyPage.showDebloatSummary || readyPage.showAdvancedPage) ? 0.0 : 1.0

				Behavior on opacity { NumberAnimation { duration: 500 } }

				Image {
					source: "../../media/talon_icon.png"
					width: 34
					height: 34
					fillMode: Image.PreserveAspectFit
					smooth: true
				}

				Text {
					text: "TALON"
					color: "#FFFFFF"
					font.family: sarpanchFont.name
					font.pixelSize: 28
					font.bold: true
					anchors.verticalCenter: parent.verticalCenter
					verticalAlignment: Text.AlignVCenter
				}
			}

			BrowserSelectionPage {
				anchors.fill: parent
				opacity: readyPage.showBrowserSelection && !readyPage.showDebloatSummary && !readyPage.showAdvancedPage && !readyPage.transitionToSummaryInProgress ? 1.0 : 0.0
				visible: opacity > 0.0
				browsers: readyPage.browsers
				selectedBrowser: readyPage.selectedBrowser
				interFontFamily: interFont.name
				localizer: localizer
				Behavior on opacity { NumberAnimation { duration: 500 } }
				onBrowserSelected: function(packageId, browserName) {
					if (readyPage.transitionToSummaryInProgress || readyPage.showDebloatSummary)
						return
					readyPage.selectedBrowser = packageId
					readyPage.selectedBrowserName = browserName
					bridge.selectBrowser(packageId, browserName)
					readyPage.refreshConfigItems()
					readyPage.transitionToSummaryInProgress = true
					browserToSummaryTimer.restart()
				}
				onSkipRequested: {
					if (readyPage.transitionToSummaryInProgress || readyPage.showDebloatSummary)
						return
					readyPage.selectedBrowser = ""
					readyPage.selectedBrowserName = ""
					bridge.skipBrowserInstall()
					readyPage.refreshConfigItems()
					readyPage.transitionToSummaryInProgress = true
					browserToSummaryTimer.restart()
				}
			}

			ReviewPlanPage {
				anchors.fill: parent
				opacity: readyPage.showDebloatSummary ? 1.0 : 0.0
				visible: opacity > 0.0
				configItems: readyPage.configItems
				presetOptions: readyPage.presetOptions
				selectedPresetKey: readyPage.selectedPresetKey
				internetAvailable: window.internetAvailable
				interFontFamily: interFont.name
				localizer: localizer
				Behavior on opacity { NumberAnimation { duration: 500 } }
				onRemoveItem: function(index) {
					bridge.removeInstallPlanItem(index)
					readyPage.refreshConfigItems()
					readyPage.refreshPresetOptions()
				}
				onResetDefaults: {
					bridge.resetInstallPlanDefaults()
					readyPage.refreshConfigItems()
					readyPage.refreshAdvancedArgs()
					readyPage.refreshPresetOptions()
				}
				onPresetRequested: function(key) {
					bridge.selectPreset(key)
					readyPage.refreshLocalizedModels()
				}
				onBackRequested: {
					readyPage.showDebloatSummary = false
					readyPage.transitionToSummaryInProgress = false
					readyPage.showBrowserSelection = true
				}
				onAdvancedRequested: {
					readyPage.showDebloatSummary = false
					readyPage.showAdvancedPage = true
					readyPage.refreshAdvancedArgs()
				}
				onStartRequested: bridge.startDebloat()
			}

			AdvancedSettingsPage {
				anchors.fill: parent
				opacity: readyPage.showAdvancedPage ? 1.0 : 0.0
				visible: opacity > 0.0
				advancedArgs: readyPage.advancedArgs
				internetAvailable: window.internetAvailable
				groupPolicyAvailable: bridge.isGroupPolicyAvailable()
				interFontFamily: interFont.name
				localizer: localizer
				Behavior on opacity { NumberAnimation { duration: 500 } }
				onImportPlan: {
					bridge.importInstallPlan()
					window.refreshPlanViews()
				}
				onImportWinUtil: {
					bridge.importWinUtilConfig()
					window.refreshPlanViews()
				}
				onEditWin11Args: readyPage.openWin11ArgsDialog()
				onEditRegistryChanges: readyPage.openRegistryChangesDialog()
				onEditProgramPackages: readyPage.openProgramPackagesDialog()
				onEditGroupPolicyChanges: readyPage.openGroupPolicyChangesDialog()
				onExportPlan: bridge.exportInstallPlan()
				onSetBackground: {
					bridge.setAppliedBackground()
					window.refreshPlanViews()
				}
				onToggleArg: function(key) {
					bridge.toggleAdvancedArg(key)
					window.refreshPlanViews()
					readyPage.refreshPresetOptions()
				}
				onConfirm: {
					readyPage.showAdvancedPage = false
					readyPage.showDebloatSummary = true
					readyPage.refreshConfigItems()
				}
			}

			AdvancedTextDialog {
				id: advancedDialog
				interFontFamily: interFont.name
				monoFontFamily: cascadiaMonoFont.name
				localizer: localizer
				onSaveRequested: function(mode, text) {
					var ok = false
					if (mode === "win11debloat")
						ok = bridge.saveWin11DebloatArgsText(text)
					else if (mode === "registry-changes")
						ok = bridge.saveRegistryChangesText(text)
					else if (mode === "program-packages")
						ok = bridge.saveChocolateyPackagesText(text)
					else if (mode === "group-policy")
						ok = bridge.saveGroupPolicyChangesText(text)
					if (ok) {
						advancedDialog.closeDialog()
						window.refreshPlanViews()
					}
				}
			}
		}
	}
}
