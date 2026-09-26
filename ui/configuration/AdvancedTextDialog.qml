import QtQuick 2.15

Rectangle {
	id: root
	anchors.fill: parent
	visible: false
	color: "#80000000"
	z: 200

	property string mode: ""
	property string titleText: ""
	property string editorText: ""
	property string helpKey: ""
	property string interFontFamily: ""
	property string monoFontFamily: ""
	property var localizer
	signal saveRequested(string mode, string text)

	function openDialog(title, text, dialogMode, dialogHelpKey) {
		titleText = title
		editorText = text
		mode = dialogMode
		helpKey = dialogHelpKey || ""
		advancedDialogEditor.text = editorText
		editorFlick.contentY = 0
		visible = true
		advancedDialogEditor.forceActiveFocus()
	}

	function closeDialog() {
		visible = false
		mode = ""
	}

	MouseArea {
		anchors.fill: parent
		acceptedButtons: Qt.LeftButton
		hoverEnabled: true
		onClicked: {}
		onWheel: wheel.accepted = true
	}

	Rectangle {
		id: frame
		width: Math.min(parent.width - 80, 760)
		height: Math.min(parent.height - 80, 500)
		anchors.centerIn: parent
		color: "#000000"
		border.color: "#2A2A2A"
		border.width: 1

		Rectangle {
			id: bar
			anchors.top: parent.top
			anchors.left: parent.left
			anchors.right: parent.right
			height: 30
			color: "#000000"

			Text {
				anchors.left: parent.left
				anchors.leftMargin: 10
				anchors.verticalCenter: parent.verticalCenter
				text: root.titleText
				color: "#FFFFFF"
				font.family: root.interFontFamily
				font.pixelSize: 12
			}

			Rectangle {
				anchors.right: parent.right
				anchors.top: parent.top
				anchors.bottom: parent.bottom
				width: 28
				color: closeMouse.containsMouse ? "#B00020" : "transparent"

				Canvas {
					anchors.centerIn: parent
					width: 12
					height: 12
					renderTarget: Canvas.Image

					onPaint: {
						var ctx = getContext("2d")
						ctx.setTransform(1, 0, 0, 1, 0, 0)
						ctx.clearRect(0, 0, width, height)
						ctx.strokeStyle = "#FFFFFF"
						ctx.lineWidth = 1
						ctx.lineCap = "square"
						ctx.lineJoin = "miter"
						var offset = 0.5
						ctx.beginPath()
						ctx.moveTo(offset, offset)
						ctx.lineTo(width - offset, height - offset)
						ctx.moveTo(width - offset, offset)
						ctx.lineTo(offset, height - offset)
						ctx.stroke()
					}
				}

				MouseArea {
					id: closeMouse
					anchors.fill: parent
					hoverEnabled: true
					cursorShape: Qt.PointingHandCursor
					onClicked: root.closeDialog()
				}
			}
		}

		Text {
			id: editorHelp
			anchors.top: bar.bottom
			anchors.topMargin: root.helpKey ? 14 : 0
			anchors.left: parent.left
			anchors.right: parent.right
			anchors.leftMargin: 14
			anchors.rightMargin: 14
			visible: root.helpKey.length > 0
			text: root.helpKey ? root.localizer.text(root.helpKey) : ""
			color: "#B0B0B0"
			font.family: root.interFontFamily
			font.pixelSize: 12
			wrapMode: Text.WordWrap
		}

		Rectangle {
			anchors.top: editorHelp.bottom
			anchors.topMargin: 14
			anchors.left: parent.left
			anchors.right: parent.right
			anchors.leftMargin: 14
			anchors.rightMargin: 14
			anchors.bottom: actionsRow.top
			anchors.bottomMargin: 14
			color: "#000000"
			border.color: "#2A2A2A"
			border.width: 1
			clip: true

			Flickable {
				id: editorFlick
				anchors.fill: parent
				anchors.margins: 8
				contentWidth: width
				contentHeight: Math.max(height, advancedDialogEditor.paintedHeight + 4)
				boundsBehavior: Flickable.StopAtBounds

				TextEdit {
					id: advancedDialogEditor
					width: editorFlick.width
					text: ""
					color: "#FFFFFF"
					font.family: root.monoFontFamily
					font.pixelSize: 14
					wrapMode: TextEdit.Wrap
					selectByMouse: true
					persistentSelection: true
					cursorVisible: activeFocus
				}
			}
		}

		Row {
			id: actionsRow
			anchors.right: parent.right
			anchors.bottom: parent.bottom
			anchors.rightMargin: 14
			anchors.bottomMargin: 14
			spacing: 8

			Rectangle {
				width: cancelLabel.implicitWidth + 22
				height: 30
				color: cancelMouse.containsMouse ? "#101010" : "#000000"
				border.width: 1
				border.color: "#2A2A2A"

				Text {
					id: cancelLabel
					anchors.centerIn: parent
					text: root.localizer.text("configuration.dialogs.cancel")
					color: "#FFFFFF"
					font.family: root.interFontFamily
					font.pixelSize: 14
				}

				MouseArea {
					id: cancelMouse
					anchors.fill: parent
					hoverEnabled: true
					cursorShape: Qt.PointingHandCursor
					onClicked: root.closeDialog()
				}
			}

			Rectangle {
				width: saveLabel.implicitWidth + 22
				height: 30
				color: saveMouse.containsMouse ? "#EAEAEA" : "#FFFFFF"
				border.width: 1
				border.color: "#FFFFFF"

				Text {
					id: saveLabel
					anchors.centerIn: parent
					text: root.localizer.text("configuration.dialogs.save_changes")
					color: "#000000"
					font.family: root.interFontFamily
					font.pixelSize: 14
				}

				MouseArea {
					id: saveMouse
					anchors.fill: parent
					hoverEnabled: true
					cursorShape: Qt.PointingHandCursor
					onClicked: root.saveRequested(root.mode, advancedDialogEditor.text)
				}
			}
		}
	}
}
