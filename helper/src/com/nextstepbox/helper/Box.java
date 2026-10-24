package com.nextstepbox.helper;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Point;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.AlarmClock;
import android.util.Base64;
import android.view.Display;
import android.view.InputDevice;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * The NextStep Box's helper on an Android phone.
 *
 * It runs only while the box is plugged in: the box starts it with `am instrument -w`, and when the
 * cable goes, adb drops and Android ends it. It answers one JSON request per line on a local socket
 * that only adb (the shell user) may use, and it has no internet permission.
 *
 * Why it exists: reading the screen takes ~1.1 s with `uiautomator dump` (a new process every time);
 * here the accessibility tree is already connected, so a read takes tens of milliseconds. It can
 * also type any language (Hindi, Kannada...) and set alarms in one step.
 */
public class Box extends Instrumentation {
    static final int VERSION = 2;
    static final String SOCKET = "nextstep-box-helper";
    static final int SHELL_UID = 2000;
    static final int MAX_TEXT = 200;

    private UiAutomation ua;
    private volatile boolean running = true;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();  // calls onStart() on a new thread
    }

    @Override
    public void onStart() {
        // Keep the user's own accessibility services (TalkBack, Select to Speak...) running.
        ua = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        AccessibilityServiceInfo info = ua.getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        ua.setServiceInfo(info);

        Bundle result = new Bundle();
        try (LocalServerSocket server = new LocalServerSocket(SOCKET)) {
            while (running) {
                LocalSocket client = server.accept();
                int uid = client.getPeerCredentials().getUid();
                if (uid != SHELL_UID && uid != 0) {  // other apps on the phone may not drive it
                    client.close();
                    continue;
                }
                serve(client);  // one client at a time: the box
            }
        } catch (Exception e) {
            result.putString("error", String.valueOf(e));
            finish(1, result);
            return;
        }
        finish(0, result);
    }

    private void serve(LocalSocket client) {
        try (LocalSocket c = client;
             BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
            OutputStream out = c.getOutputStream();
            String line;
            while (running && (line = in.readLine()) != null) {
                JSONObject res;
                try {
                    res = handle(new JSONObject(line));
                } catch (Exception e) {
                    res = fail(e.getClass().getSimpleName() + ": " + e.getMessage());
                }
                out.write((res.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        } catch (Exception ignored) {
            // the box went away; wait for it to reconnect
        }
    }

    private JSONObject handle(JSONObject req) throws Exception {
        String cmd = req.getString("cmd");
        switch (cmd) {
            case "ping":
                return ok().put("version", VERSION).put("sdk", Build.VERSION.SDK_INT);
            case "dump":
                return dump();
            case "screenshot":
                return screenshot(req.optInt("max_w", 720), req.optInt("quality", 60));
            case "settle":
                return ok().put("ms", settle(req.optInt("min_ms", 120), req.optInt("max_ms", 2500)));
            case "tap": {
                int x = req.getInt("x"), y = req.getInt("y");
                touch(x, y, x, y, req.optInt("hold_ms", 0));
                return ok();
            }
            case "swipe":
                touch(req.getInt("x1"), req.getInt("y1"), req.getInt("x2"), req.getInt("y2"), req.optInt("ms", 400));
                return ok();
            case "key":
                return key(req.getInt("code"));
            case "set_text":
                return setText(req.getString("text"));
            case "enter":
                return enter();
            case "set_alarm":
                return setAlarm(req.getInt("hour"), req.getInt("minute"), req.optString("label", ""));
            case "set_timer":
                return setTimer(req.getInt("seconds"), req.optString("label", ""));
            case "quit":
                running = false;
                return ok();
            default:
                return fail("unknown_cmd:" + cmd);
        }
    }

    // ---- eyes ------------------------------------------------------------------------------------

    /** Same node shape as the box's uiautomator parser (box/drivers/android_adb.py parse_ui_xml). */
    private JSONObject dump() throws JSONException {
        if (Build.VERSION.SDK_INT >= 34) ua.clearCache();
        AccessibilityNodeInfo root = null;
        for (int i = 0; i < 10 && root == null; i++) {
            root = ua.getRootInActiveWindow();
            if (root == null) SystemClock.sleep(30);
        }
        Point size = screenSize();
        JSONObject res = ok().put("w", size.x).put("h", size.y);
        JSONArray nodes = new JSONArray();
        boolean[] secure = {false};
        if (root != null) walk(root, nodes, secure, new Rect(0, 0, size.x, size.y), 0);
        return res.put("package", root == null ? "" : String.valueOf(root.getPackageName()))
                .put("nodes", nodes).put("secure", secure[0]);
    }

    private void walk(AccessibilityNodeInfo n, JSONArray out, boolean[] secure, Rect screen, int depth) throws JSONException {
        if (depth > 80) return;
        if (n.isVisibleToUser()) {
            Rect b = new Rect();
            n.getBoundsInScreen(b);
            if (b.intersect(screen) && b.width() > 0 && b.height() > 0) {
                String cls = n.getClassName() == null ? "" : n.getClassName().toString();
                CharSequence text = n.getText(), desc = n.getContentDescription();
                boolean hasText = text != null && text.length() > 0, hasDesc = desc != null && desc.length() > 0;
                boolean click = n.isClickable() || n.isLongClickable();
                boolean edit = n.isEditable() || cls.contains("EditText");
                if (hasText || hasDesc || click || edit || n.isScrollable()) {
                    JSONObject o = new JSONObject().put("i", out.length()).put("cls", cls.substring(cls.lastIndexOf('.') + 1))
                            .put("b", new JSONArray().put(b.left).put(b.top).put(b.right).put(b.bottom));
                    if (n.isPassword()) {
                        o.put("secure", true);  // never send what is typed in a password field
                        secure[0] = true;
                    } else if (hasText) {
                        o.put("text", cut(text));
                    }
                    if (hasDesc) o.put("desc", cut(desc));
                    String id = n.getViewIdResourceName();
                    if (id != null) o.put("id", id.contains(":id/") ? id.substring(id.indexOf(":id/") + 4) : id);
                    if (click) o.put("click", true);
                    if (edit) o.put("edit", true);
                    if (n.isScrollable()) o.put("scroll", true);
                    if (n.isFocused()) o.put("focus", true);
                    if (Build.VERSION.SDK_INT >= 26 && n.isShowingHintText()) o.put("hint", true);
                    out.put(o);
                }
            }
        }
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c != null) {
                walk(c, out, secure, screen, depth + 1);
                c.recycle();
            }
        }
    }

    private JSONObject screenshot(int maxW, int quality) throws JSONException {
        Bitmap shot = software(ua.takeScreenshot());
        if (shot == null) return fail("no_screenshot");
        float scale = Math.min(1f, maxW / (float) shot.getWidth());
        Bitmap small = scale < 1f
                ? Bitmap.createScaledBitmap(shot, Math.round(shot.getWidth() * scale), Math.round(shot.getHeight() * scale), true)
                : shot;
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        small.compress(Bitmap.CompressFormat.JPEG, quality, buf);
        return ok().put("jpeg_b64", Base64.encodeToString(buf.toByteArray(), Base64.NO_WRAP));
    }

    /** Waits until two frames in a row are the same (the screen stopped moving); returns the ms waited. */
    private long settle(int minMs, int maxMs) {
        long start = SystemClock.uptimeMillis();
        SystemClock.sleep(minMs);
        Bitmap prev = thumb();
        while (SystemClock.uptimeMillis() - start < maxMs) {
            SystemClock.sleep(60);
            Bitmap cur = thumb();
            if (prev != null && cur != null && cur.sameAs(prev)) break;
            prev = cur;
        }
        return SystemClock.uptimeMillis() - start;
    }

    private Bitmap thumb() {
        Bitmap shot = software(ua.takeScreenshot());
        return shot == null ? null : Bitmap.createScaledBitmap(shot, Math.max(1, shot.getWidth() / 8),
                Math.max(1, shot.getHeight() / 8), false);
    }

    private static Bitmap software(Bitmap b) {
        if (b != null && Build.VERSION.SDK_INT >= 26 && b.getConfig() == Bitmap.Config.HARDWARE) {
            return b.copy(Bitmap.Config.ARGB_8888, false);
        }
        return b;
    }

    private Point screenSize() {
        DisplayManager dm = (DisplayManager) getContext().getSystemService(Context.DISPLAY_SERVICE);
        Point p = new Point();
        dm.getDisplay(Display.DEFAULT_DISPLAY).getRealSize(p);
        return p;
    }

    // ---- hands -----------------------------------------------------------------------------------

    /** A tap (same start and end) or a swipe; times are faked forward so it takes `ms` exactly. */
    private void touch(int x1, int y1, int x2, int y2, int ms) {
        long down = SystemClock.uptimeMillis();
        inject(MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN, x1, y1, 0));
        boolean moves = x1 != x2 || y1 != y2;
        int steps = moves ? Math.max(ms / 10, 5) : 0;
        for (int i = 1; i <= steps; i++) {
            float f = i / (float) steps;
            long t = down + (long) (ms * f);
            sleepUntil(t);
            inject(MotionEvent.obtain(down, t, MotionEvent.ACTION_MOVE, x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, 0));
        }
        sleepUntil(down + ms);
        inject(MotionEvent.obtain(down, SystemClock.uptimeMillis(), MotionEvent.ACTION_UP, x2, y2, 0));
    }

    private void inject(MotionEvent ev) {
        ev.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        ua.injectInputEvent(ev, true);
        ev.recycle();
    }

    private static void sleepUntil(long t) {
        long wait = t - SystemClock.uptimeMillis();
        if (wait > 0) SystemClock.sleep(wait);
    }

    private JSONObject key(int code) throws JSONException {
        int global = code == KeyEvent.KEYCODE_BACK ? AccessibilityService.GLOBAL_ACTION_BACK
                : code == KeyEvent.KEYCODE_HOME ? AccessibilityService.GLOBAL_ACTION_HOME
                : code == KeyEvent.KEYCODE_APP_SWITCH ? AccessibilityService.GLOBAL_ACTION_RECENTS : -1;
        if (global >= 0) return ua.performGlobalAction(global) ? ok() : fail("global_action_failed");
        long t = SystemClock.uptimeMillis();
        for (int action : new int[]{KeyEvent.ACTION_DOWN, KeyEvent.ACTION_UP}) {
            ua.injectInputEvent(new KeyEvent(t, SystemClock.uptimeMillis(), action, code, 0, 0,
                    KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, InputDevice.SOURCE_KEYBOARD), true);
        }
        return ok();
    }

    /** Replaces the focused field's text: works for every language, unlike `input text`. */
    private JSONObject setText(String text) throws JSONException {
        AccessibilityNodeInfo f = ua.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (f == null || !f.isEditable()) return fail("no_focused_field");
        if (f.isPassword()) return fail("password_field");  // the box never types secrets
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        if (!f.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return fail("set_text_refused");
        Bundle sel = new Bundle();
        sel.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, text.length());
        sel.putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, text.length());
        f.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, sel);
        return ok();
    }

    private JSONObject enter() throws JSONException {
        if (Build.VERSION.SDK_INT >= 30) {
            AccessibilityNodeInfo f = ua.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
            if (f != null && f.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId())) return ok();
        }
        return key(KeyEvent.KEYCODE_ENTER);
    }

    private JSONObject setAlarm(int hour, int minute, String label) throws JSONException {
        Intent i = new Intent(AlarmClock.ACTION_SET_ALARM)
                .putExtra(AlarmClock.EXTRA_HOUR, hour)
                .putExtra(AlarmClock.EXTRA_MINUTES, minute)
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (!label.isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, label);
        if (i.resolveActivity(getContext().getPackageManager()) == null) return fail("no_clock_app");
        getContext().startActivity(i);
        return ok();
    }

    private JSONObject setTimer(int seconds, String label) throws JSONException {
        Intent i = new Intent(AlarmClock.ACTION_SET_TIMER)
                .putExtra(AlarmClock.EXTRA_LENGTH, seconds)
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (!label.isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, label);
        if (i.resolveActivity(getContext().getPackageManager()) == null) return fail("no_clock_app");
        getContext().startActivity(i);
        return ok();
    }

    // ---- replies ---------------------------------------------------------------------------------

    private static String cut(CharSequence s) {
        String t = s.toString();
        return t.length() > MAX_TEXT ? t.substring(0, MAX_TEXT) : t;
    }

    private static JSONObject ok() throws JSONException {
        return new JSONObject().put("ok", true);
    }

    private static JSONObject fail(String error) {
        try {
            return new JSONObject().put("ok", false).put("error", error);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
    }
}
