from box.drivers.android_adb import parse_ui_xml
from box.drivers.base import px

XML = """junk before <?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.android.chrome" content-desc="" clickable="false" password="false" bounds="[0,0][1080,2280]">
  <node index="1" text="Search or type web address" resource-id="com.android.chrome:id/search_box_text" class="android.widget.EditText" package="com.android.chrome" content-desc="" clickable="true" focused="true" password="false" scrollable="false" bounds="[42,300][1038,420]" />
  <node index="2" text="" resource-id="" class="android.widget.EditText" package="com.android.chrome" content-desc="" clickable="true" password="true" bounds="[42,500][1038,600]" />
  <node index="3" text="" resource-id="" class="android.view.View" package="com.android.chrome" content-desc="" clickable="false" password="false" bounds="[0,0][0,0]" />
  <node index="4" text="" resource-id="" class="android.widget.ImageButton" package="com.android.chrome" content-desc="More options" clickable="true" password="false" bounds="[960,80][1080,200]" />
</node></hierarchy>"""


def test_parse_keeps_meaningful_visible_nodes_and_hides_passwords():
    pkg, nodes, secure = parse_ui_xml(XML)
    assert pkg == "com.android.chrome"
    assert secure is True
    assert [n.get("text") or n.get("desc") or ("<secure>" if n.get("secure") else "") for n in nodes] == [
        "Search or type web address", "<secure>", "More options"]
    search = nodes[0]
    assert search["edit"] and search["click"] and search["focus"] and search["id"] == "search_box_text"
    assert "text" not in nodes[1]  # a password field's text is never sent


def test_px_maps_normalised_coordinates():
    assert px(0, 1080) == 0 and px(500, 1080) == 540 and px(999, 1080) == 1078 and px(5000, 1080) == 1078
