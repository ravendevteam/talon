import QtQuick 2.15

Item {
	id: root
	property var advancedArgs: []
	property bool internetAvailable: true
	property bool groupPolicyAvailable: false
	property string interFontFamily: ""
	property var localizer
	signal importPlan()
	signal importWinUtil()
	signal editWin11Args()
	signal editRegistryChanges()
	signal editProgramPackages()
	signal editGroupPolicyChanges()
	signal exportPlan()
	signal setBackground()
	signal toggleArg(string key)
	signal confirm()

	Text {
		anchors.top: parent.top
		anchors.topMargin: 40
		anchors.horizontalCenter: parent.horizontalCenter
		text: root.localizer.text("configuration.advanced.title")
		color: "#FFFFFF"
		font.family: root.interFontFamily
		font.pixelSize: 22
	}

	Row {
		anchors.top: parent.top
		anchors.topMargin: 90
		anchors.horizontalCenter: parent.horizontalCenter
		spacing: 8
		Image { source: "../../media/icon_warning.png"; width: 24; height: 24; fillMode: Image.PreserveAspectFit; smooth: true }
		Text {
			anchors.verticalCenter: parent.verticalCenter
			width: Math.min(implicitWidth, root.width - 120)
			text: root.localizer.text("configuration.advanced.warning")
			color: "#FF0000"
			font.family: root.interFontFamily
			font.pixelSize: 15
			wrapMode: Text.WordWrap
		}
	}

	Flow {
		id: advancedActionsRow
		anchors.top: parent.top
		anchors.topMargin: 132
		anchors.left: parent.left
		anchors.right: parent.right
		anchors.leftMargin: 36
		anchors.rightMargin: 36
		spacing: 10

		Repeater {
			model: [
				{"label": root.localizer.text("configuration.advanced.import_plan"), "action": "importPlan"},
				{"label": root.localizer.text("configuration.advanced.import_winutil"), "action": "importWinUtil"},
				{"label": root.localizer.text("configuration.advanced.set_win11_args"), "action": "win11"},
				{"label": root.localizer.text("configuration.advanced.edit_registry_changes"), "action": "registry"},
				{"label": root.localizer.text("configuration.advanced.edit_program_packages"), "action": "programs"},
				{"label": root.localizer.text("configuration.advanced.edit_group_policy_changes"), "action": "groupPolicy"},
				{"label": root.localizer.text("configuration.advanced.export_plan"), "action": "export"},
				{"label": root.localizer.text("configuration.advanced.set_background"), "action": "background"}
			]

			Rectangle {
				property bool actionAvailable: modelData.action !== "groupPolicy" || root.groupPolicyAvailable
				width: Math.min(Math.max(actionLabel.implicitWidth + 22, 120), advancedActionsRow.width)
				height: Math.max(30, actionLabel.implicitHeight + 12)
				color: actionMouse.containsMouse ? "#101010" : "#000000"
				border.width: 1
				border.color: "#2A2A2A"
				opacity: actionAvailable ? 1.0 : 0.45

				Text {
					id: actionLabel
					anchors.centerIn: parent
					text: modelData.label
					color: "#FFFFFF"
					font.family: root.interFontFamily
					font.pixelSize: 14
					width: parent.width - 16
					horizontalAlignment: Text.AlignHCenter
					wrapMode: Text.WordWrap
				}

				MouseArea {
					id: actionMouse
					anchors.fill: parent
					hoverEnabled: true
					enabled: parent.actionAvailable
					cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
					onClicked: {
						if (modelData.action === "importPlan")
							root.importPlan()
						else if (modelData.action === "importWinUtil")
							root.importWinUtil()
						else if (modelData.action === "win11")
							root.editWin11Args()
						else if (modelData.action === "registry")
							root.editRegistryChanges()
						else if (modelData.action === "programs")
							root.editProgramPackages()
						else if (modelData.action === "groupPolicy")
							root.editGroupPolicyChanges()
						else if (modelData.action === "export")
							root.exportPlan()
						else if (modelData.action === "background")
							root.setBackground()
					}
				}
			}
		}
	}

	ListView {
		id: advancedArgsList
		anchors.top: advancedActionsRow.bottom
		anchors.topMargin: 12
		anchors.bottom: confirmButtonWrap.top
		anchors.bottomMargin: 18
		anchors.left: parent.left
		anchors.leftMargin: 36
		anchors.right: parent.right
		anchors.rightMargin: 36
		clip: true
		model: root.advancedArgs

		delegate: Item {
			width: advancedArgsList.width
			height: Math.max(42, optionLabels.implicitHeight + 12)
			property bool unavailable: modelData.available === false || (!root.internetAvailable && (modelData.key === "browser-installation" || modelData.key === "program-installation"))
			property string unavailableReason: modelData.unavailableReason || (unavailable ? root.localizer.text("configuration.advanced.internet_required") : "")

			Column {
				id: optionLabels
				anchors.left: parent.left
				anchors.right: valueButton.left
				anchors.rightMargin: 12
				anchors.verticalCenter: parent.verticalCenter
				spacing: 3

				Text {
					width: parent.width
					text: modelData.label
					color: unavailable ? "#7A7A7A" : "#FFFFFF"
					font.family: root.interFontFamily
					font.pixelSize: 16
					wrapMode: Text.NoWrap
					elide: Text.ElideRight
				}

				Text {
					width: parent.width
					visible: unavailableReason.length > 0
					text: unavailableReason
					color: "#A0A0A0"
					font.family: root.interFontFamily
					font.pixelSize: 12
					wrapMode: Text.WordWrap
				}
			}

			Rectangle {
				id: valueButton
				width: 72
				height: 28
				anchors.right: parent.right
				anchors.verticalCenter: parent.verticalCenter
				color: unavailable ? "#050505" : (valueMouse.containsMouse ? "#111111" : "#000000")
				border.width: 1
				border.color: unavailable ? "#1A1A1A" : "#2A2A2A"

				Text {
					anchors.centerIn: parent
					text: modelData.value ? root.localizer.text("configuration.advanced.true") : root.localizer.text("configuration.advanced.false")
					color: unavailable ? "#7A7A7A" : "#FFFFFF"
					font.family: root.interFontFamily
					font.pixelSize: 14
				}

				MouseArea {
					id: valueMouse
					anchors.fill: parent
					hoverEnabled: true
					enabled: !unavailable
					cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
					onClicked: root.toggleArg(modelData.key)
				}
			}

			Rectangle {
				visible: index < advancedArgsList.count - 1
				anchors.left: parent.left
				anchors.right: parent.right
				anchors.bottom: parent.bottom
				height: 1
				color: "#2A2A2A"
			}
		}
	}

	Text {
		anchors.left: parent.left
		anchors.leftMargin: 36
		anchors.bottom: parent.bottom
		anchors.bottomMargin: 28
		text: root.localizer.text("configuration.advanced.see_documentation")
		color: seeDocsMouse.containsMouse ? "#FFFFFF" : "#A0A0A0"
		font.family: root.interFontFamily
		font.pixelSize: 15

		MouseArea {
			id: seeDocsMouse
			anchors.fill: parent
			hoverEnabled: true
			cursorShape: Qt.PointingHandCursor
			onClicked: Qt.openUrlExternally("https://github.com/ravendevteam/talon/blob/main/DOCUMENTATION.md")
		}
	}

	Item {
		id: confirmButtonWrap
		width: 98
		height: 38
		anchors.right: parent.right
		anchors.rightMargin: 22
		anchors.bottom: parent.bottom
		anchors.bottomMargin: 22

		Rectangle {
			anchors.fill: parent
			color: "transparent"
			border.width: 1
			border.color: "#FFFFFF"
			opacity: 0.45
		}

		Rectangle {
			anchors.fill: parent
			anchors.margins: 3
			color: confirmMouse.containsMouse ? "#1A1A1A" : "#000000"

			Text {
				anchors.centerIn: parent
				text: root.localizer.text("configuration.advanced.confirm")
				color: "#FFFFFF"
				font.family: root.interFontFamily
				font.pixelSize: 15
			}

			MouseArea {
				id: confirmMouse
				anchors.fill: parent
				hoverEnabled: true
				cursorShape: Qt.PointingHandCursor
				onClicked: root.confirm()
			}
		}
	}
}
