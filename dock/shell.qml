import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Io
import "DockLayout.js" as DockLayout

ShellRoot {
    id: root
    property var pins: ["google-chrome", "discord", "claude-web", "chatgpt", "spotify", "t3code", "com.microsoft.VSCode", "obsidian", "foot", "localsend"]
    property var busy: ({})
    property var panels: []
    property bool review: false
    readonly property int slotWidth: 45
    readonly property int bodyHeight: 64
    readonly property int iconBase: 34
    readonly property int iconPeak: 58
    property var iconIndex: ({})
    // Cached presentation artwork preserves existing app frames and original logos.
    property var preparedIcons: ({})
    readonly property string artworkRequest: JSON.stringify(apps.map(e => ({id:e.id,source:originalIcon(e)})))
    onArtworkRequestChanged: artworkRefresh.restart()
    Process {
        id: artworkScan
        property string request: "[]"
        command: ["python3", Qt.resolvedUrl("prepare-icons.py").toString().replace("file://", ""), request]
        stdout: StdioCollector { onStreamFinished: {
            try { root.preparedIcons = JSON.parse(text); } catch(e) { console.warn("Dock artwork:", e); }
        } }
        onRunningChanged: if (!running && request !== root.artworkRequest) artworkRefresh.restart()
    }
    Timer {
        id: artworkRefresh; interval: 120
        onTriggered: {
            if (artworkScan.running) return;
            artworkScan.request = root.artworkRequest;
            artworkScan.running = true;
        }
    }
    Process {
        id: iconScan
        command: ["python3", Qt.resolvedUrl("icon-index.py").toString().replace("file://", "")]
        stdout: StdioCollector { onStreamFinished: { try { root.iconIndex = JSON.parse(text); } catch(e) { console.warn("Icon index:",e); } } }
    }
    Timer { id: iconRefresh; interval: 500; onTriggered: iconScan.running = true }
    Connections { target: DesktopEntries.applications; function onValuesChanged() { iconRefresh.restart(); } }
    Component.onCompleted: iconScan.running = true
    readonly property var entries: DesktopEntries.applications.values
    readonly property var apps: pins.map(id => entries.find(e => e.id === id)).filter(e => !!e)
    function norm(s) { return String(s || "").toLowerCase().replace(/\.desktop$/, ""); }
    function matches(e, t) {
        const app = norm(t.appId), id = norm(e.id), cls = norm(e.startupClass);
        if (id === "claude-web") return app === "claude-web" || app.indexOf("claude.ai") >= 0;
        if (id === "google-chrome") return app === "google-chrome" || app === "google-chrome-stable";
        return app === id || (!!cls && app === cls) || app === norm(e.name) ||
            (id === "com.microsoft.vscode" && app === "code") || (id === "obsidian" && app === "obsidian");
    }
    function windows(e) { return ToplevelManager.toplevels.values.filter(t => matches(e,t)); }
    function originalIcon(e) {
        if (!e) return "";
        const v = e.icon || "application-x-executable";
        return v.startsWith("/") ? "file://" + v : (root.iconIndex[v] ? "file://" + root.iconIndex[v] : (Quickshell.iconPath(v, true) || Quickshell.iconPath("application-x-executable")));
    }
    function icon(e) {
        const original = originalIcon(e);
        return preparedIcons[original] ? preparedIcons[original].source : original;
    }
    function activate(e, newWindow) {
        const ws = windows(e);
        if (ws.length && !newWindow) {
            const active = ws.findIndex(w => w.activated);
            ws[(active + 1) % ws.length].activate();
            return false;
        }
        if (busy[e.id]) return false;
        busy = Object.assign({}, busy, { [e.id]: Date.now() });
        Quickshell.execDetached(["uwsm-app", "--", "gtk-launch", e.id + ".desktop"]);
        return true;
    }
    function savePins(next) { pins = next; settings.setText(JSON.stringify({pins: next}, null, 2)); }
    function movePin(id, delta) {
        const p = pins.slice(), i = p.indexOf(id), j = i + delta;
        if (i < 0 || j < 0 || j >= p.length) return;
        p.splice(i, 1); p.splice(j, 0, id); savePins(p);
    }
    FileView {
        id: settings
        path: Quickshell.env("HOME") + "/.config/quickshell/classic-dock/settings.json"
        watchChanges: true
        onLoaded: { try { root.pins = JSON.parse(text()).pins; } catch(e) {} }
        onFileChanged: reload()
    }
    Timer {
        interval: 500; running: Object.keys(root.busy).length > 0; repeat: true
        onTriggered: {
            const next = {};
            for (const id in root.busy) {
                const e = root.apps.find(a => a.id === id);
                if (e && !root.windows(e).length && Date.now() - root.busy[id] < 10000) next[id] = root.busy[id];
            }
            root.busy = next;
        }
    }
    IpcHandler {
        target: "dock"
        function review(show: bool): void { root.review = show; }
        function status(): string { return JSON.stringify({pins: root.pins, apps: root.apps.map(e => ({id:e.id,name:e.name,icon:root.icon(e),original:root.originalIcon(e),artwork:root.preparedIcons[root.originalIcon(e)],windows:root.windows(e).length})), panels: root.panels.map(p => p.snapshot())}); }
        function animate(index: int): void { root.panels.forEach(p => p.animate(index)); }
        function add(monitor: string): void { const p=root.panels.find(p=>p.screen.name===monitor); if(p)p.showPicker(); }
    }
    Variants {
        model: Quickshell.screens
        PanelWindow {
            id: dock
            required property var modelData
            screen: modelData
            anchors.bottom: true
            implicitWidth: Math.min(screen.width, root.apps.length * root.slotWidth + 280)
            implicitHeight: 150
            color: "transparent"
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "classic-dock"
            WlrLayershell.layer: WlrLayer.Overlay
            visible: !ToplevelManager.toplevels.values.some(t => t.appId === "org.omarchy.screensaver")
            property bool revealed: false
            property real pointerX: -1000
            readonly property bool magnifying: (pointer.hovered || iconHovered) && shown && !menu.visible && !picker.visible
            property real zoom: magnifying ? 1 : 0
            Behavior on zoom { NumberAnimation { duration: dock.magnifying ? 130 : 180; easing.type: Easing.OutCubic } }
            readonly property var lens: DockLayout.layout(root.apps.length, root.slotWidth, root.iconBase, root.iconPeak, pointerX, dock.width/2, zoom)
            readonly property bool iconHovered: Array.from({length:slots.count}, (_,i) => slots.itemAt(i)).some(s => s && s.hovered)
            readonly property bool held: pointer.hovered || iconHovered || menu.visible || picker.visible || root.review
            readonly property bool shown: revealed || menu.visible || picker.visible || root.review
            property real slide: shown ? 0 : 100
            Behavior on slide { NumberAnimation { duration: dock.shown ? 200 : 180; easing.type: Easing.OutCubic } }
            onHeldChanged: { if (held) { hideDelay.stop(); revealDelay.start(); } else { revealDelay.stop(); hideDelay.restart(); } }
            Timer { id: revealDelay; interval: 70; onTriggered: dock.revealed = true }
            Timer { id: hideDelay; interval: 380; onTriggered: if (!dock.held) dock.revealed = false }
            Component.onCompleted: root.panels = root.panels.concat([dock])
            Component.onDestruction: root.panels = root.panels.filter(p => p !== dock)
            function animate(i) { const s = slots.itemAt(i); if (s) s.bounce(); }
            function showPicker() { menu.visible=false; picker.visible=true; }
            function snapshot() { return {screen:screen.name,shown:shown,menu:menu.visible,picker:picker.visible,query:search.text,slide:slide,body:{x:glass.x,y:body.y,width:glass.width,height:glass.height,radius:glass.radius},hitHeight:hit.height,slots:Array.from({length:slots.count}, (_,i) => {const s=slots.itemAt(i);return {id:s.modelData.id,x:s.x,width:s.width,height:s.height,iconSize:s.iconSize,center:s.x+s.width/2,indicator:{size:4,gap:5},scale:s.visualScale,lift:s.lift};})}; }
            Item {
                id: hit
                x: glass.x; width: glass.width
                y: dock.slide < 99 ? body.y - (dock.magnifying ? 22 : 2) : dock.height - 2
                height: dock.height - y
            }
            mask: Region { item: hit }
            // Input and painted extents are independent; only the glass is blurred.
            Item {
                anchors.fill: parent
                HoverHandler { id: pointer; onPointChanged: dock.pointerX = point.position.x }
            }
            Item {
                id: body
                x: 0; y: dock.height - root.bodyHeight - 8 + dock.slide
                width: dock.width; height: root.bodyHeight
                Rectangle {
                    id: glass
                    x: (dock.width - width) / 2; y: 0
                    // The glass never scales with hover, press or launch.
                    width: dock.lens.width + 24; height: root.bodyHeight; radius: 18
                    color: "#60384048"; border.width: 1; border.color: "#55ffffff"
                    layer.enabled: true
                    layer.effect: MultiEffect {
                        shadowEnabled: true; shadowOpacity: .15; shadowBlur: .4
                        shadowVerticalOffset: 3; shadowColor: "black"
                    }
                }
                MouseArea {
                    anchors.fill: glass; acceptedButtons: Qt.RightButton
                    onClicked: { menu.app = null; menu.slotIndex = -1; menu.visible = true; }
                }
                Item {
                    x: 0; y: 8; width: dock.width; height: 48
                    Repeater {
                        id: slots
                        model: root.apps
                        Item {
                            id: slot
                            required property var modelData
                            required property int index
                            readonly property var geometry: dock.lens.items[index] || ({x:0,width:root.slotWidth,size:root.iconBase})
                            x: geometry.x; width: geometry.width; height: 48
                            property real iconSize: geometry.size
                            property bool hovered: mouse.containsMouse
                            property var appWindows: root.windows(modelData)
                            property real lift: 0
                            property real visualScale: mouse.pressed && mouse.containsMouse && mouse.pressedButtons === Qt.LeftButton ? .96 : 1
                            Behavior on visualScale { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                            function bounce() { launchMotion.restart(); }
                            SequentialAnimation {
                                id: launchMotion
                                NumberAnimation { target: slot; property: "lift"; to: -10; duration: 160; easing.type: Easing.OutQuad }
                                NumberAnimation { target: slot; property: "lift"; to: 1; duration: 140; easing.type: Easing.InQuad }
                                NumberAnimation { target: slot; property: "lift"; to: 0; duration: 100; easing.type: Easing.OutQuad }
                            }
                            Image {
                                id: appImage
                                x: (slot.width-width)/2; y: 42-height+slot.lift; width: slot.iconSize; height: width
                                scale: slot.visualScale; source: root.icon(slot.modelData)
                                fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; sourceSize: Qt.size(256,256)
                            }
                            Rectangle { x:(slot.width-4)/2; y:47; width:4; height:4; radius:2; color:"#a6a6a8"; visible:slot.appWindows.length > 0; antialiasing:true }
                            Rectangle {
                                visible: mouse.containsMouse && !mouse.pressed && !menu.visible && !picker.visible
                                x: (slot.width - width) / 2; y: appImage.y - 36
                                width: label.implicitWidth + 20; height: 28; radius:6
                                color:"#ed29292b"; border.width:1; border.color:"#405f5f62"
                                Text { id:label; anchors.centerIn:parent; text:slot.modelData.name; font.family:"Inter"; font.pixelSize:12; color:"#f5f5f7" }
                            }
                            MouseArea {
                                id: mouse
                                x: 0; y: Math.min(0,appImage.y); width:slot.width; height:slot.height-y
                                hoverEnabled:true
                                onPositionChanged: event => { dock.pointerX = mapToItem(dock.contentItem,event.x,event.y).x; }
                                acceptedButtons:Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                                onClicked: event => {
                                    if (event.button === Qt.RightButton) { menu.app = slot.modelData; menu.slotIndex = slot.index; menu.visible = !menu.visible; }
                                    else if (root.activate(slot.modelData, event.button === Qt.MiddleButton)) slot.bounce();
                                }
                            }
                        }
                    }
                }
            }
            PanelWindow {
                id: menu
                visible: false
                screen: dock.screen
                anchors { top:true; bottom:true; left:true; right:true }
                exclusionMode: ExclusionMode.Ignore
                WlrLayershell.namespace: "classic-dock-popup"
                WlrLayershell.layer: WlrLayer.Overlay
                WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
                onVisibleChanged: if (visible) Qt.callLater(() => menuCard.forceActiveFocus())
                property var app: null
                property int slotIndex: -1
                readonly property var actions: app ? [root.windows(app).length ? "Öne getir" : "Aç", "Yeniden aç", "Sola taşı", "Sağa taşı", "Dock’tan çıkar", "Uygulama ekle…"] : ["Uygulama ekle…"]
                color:"transparent"
                MouseArea { anchors.fill:parent; onClicked:menu.visible=false }
                Rectangle {
                    id:menuCard
                    x: Math.max(8,Math.min(menu.screen.width-width-8,(menu.screen.width-dock.width)/2+(menu.slotIndex < 0 ? dock.width/2 : dock.lens.items[menu.slotIndex].center)-width/2))
                    y:menu.height-root.bodyHeight-38-height; width:216; height:menu.actions.length*31+12
                    radius:10; color:"#f02a2a2c"; border.width:1; border.color:"#775f5f62"
                    focus:true; Keys.onEscapePressed:menu.visible=false
                    MouseArea { anchors.fill:parent }
                    Column { x:6; y:6
                        Repeater { model:menu.actions
                            Rectangle {
                                required property string modelData
                                required property int index
                                width:204; height:31; radius:5
                                color:actionMouse.containsMouse ? "#3478f6" : "transparent"
                                Text { x:10; anchors.verticalCenter:parent.verticalCenter; text:modelData; font.family:"Inter"; font.pixelSize:13; color:"#f5f5f7" }
                                MouseArea { id:actionMouse; anchors.fill:parent; hoverEnabled:true
                                    onClicked: {
                                        const a=menu.app, i=index;
                                        menu.visible=false;
                                        if (!a || i===5) { picker.visible=true; return; }
                                        if (i===0 || i===1) { if(root.activate(a,i===1)) dock.animate(root.apps.findIndex(e=>e.id===a.id)); }
                                        else if (i===2 || i===3) root.movePin(a.id,i===2 ? -1 : 1);
                                        else if (i===4) root.savePins(root.pins.filter(id=>id!==a.id));
                                    }
                                }
                            }
                        }
                    }
                }
            }
            PanelWindow {
                id: picker
                visible:false
                screen:dock.screen
                anchors { top:true; bottom:true; left:true; right:true }
                color:"transparent"
                exclusionMode:ExclusionMode.Ignore
                WlrLayershell.namespace:"classic-dock-popup"
                WlrLayershell.layer:WlrLayer.Overlay
                WlrLayershell.keyboardFocus:visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
                onVisibleChanged: if(visible) { search.text=""; Qt.callLater(() => search.forceActiveFocus()); }
                MouseArea { anchors.fill:parent; onClicked:picker.visible=false }
                Rectangle {
                    x:(picker.width-width)/2; y:picker.height-root.bodyHeight-38-height; width:340; height:420
                    radius:12; color:"#f229292b"; border.width:1; border.color:"#775f5f62"
                    Keys.onEscapePressed:picker.visible=false
                    MouseArea { anchors.fill:parent }
                    Text { x:16; y:14; text:"Dock’a uygulama ekle"; color:"white"; font.family:"Inter"; font.pixelSize:14; font.weight:Font.DemiBold }
                    TextField {
                        id:search; x:12; y:43; width:316; height:34; placeholderText:"Uygulama ara…"; color:"white"; font.family:"Inter"
                        background:Rectangle { radius:6; color:"#303034"; border.color:"#55555b" }
                        Keys.onEscapePressed:picker.visible=false
                    }
                    ListView {
                        x:8; y:85; width:324; height:327; clip:true
                        model:root.entries.filter(e=>!e.noDisplay && root.pins.indexOf(e.id)<0 && e.name.toLowerCase().indexOf(search.text.toLowerCase())>=0).sort((a,b)=>a.name.localeCompare(b.name))
                        ScrollBar.vertical:ScrollBar {}
                        delegate:Rectangle {
                            required property var modelData
                            width:324; height:40; radius:6; color:addMouse.containsMouse ? "#3478f6" : "transparent"
                            Image { x:8; y:8; width:24; height:24; source:root.icon(modelData); fillMode:Image.PreserveAspectFit }
                            Text { x:42; anchors.verticalCenter:parent.verticalCenter; width:270; elide:Text.ElideRight; text:modelData.name; color:"white"; font.family:"Inter"; font.pixelSize:13 }
                            MouseArea { id:addMouse; anchors.fill:parent; hoverEnabled:true; onClicked:{root.savePins(root.pins.concat([modelData.id]));picker.visible=false;} }
                        }
                    }
                }
            }
        }
    }
}
