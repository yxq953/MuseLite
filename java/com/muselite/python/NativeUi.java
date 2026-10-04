package com.muselite.python;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RenderEffect;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Looper;
import android.os.Build;
import android.text.Html;
import android.text.InputType;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.app.AlertDialog;
import java.util.Calendar;

import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Android UI for the Python app. The transcript and composer have separate layout slots. */
public final class NativeUi {
    private static final int INK = Color.rgb(42, 55, 78);
    private static final int MUTED = Color.rgb(112, 124, 145);
    private static final int CANVAS = Color.rgb(248, 250, 255);
    private static final int WHITE = Color.WHITE;
    private static final int DEEP = Color.rgb(104, 122, 184);
    private static final int TEAL = Color.rgb(115, 151, 211);
    private static final int MINT = Color.rgb(218, 232, 255);
    private static final int LINE = Color.rgb(224, 229, 241);
    private static final int RED = Color.rgb(169, 61, 50);
    private static final int GLASS = Color.argb(255, 255, 255, 255);
    private static final String TAG = "MuseLiteUI";

    private static Activity owner;
    private static FrameLayout host;
    private static LinearLayout page;
    private static LinearLayout messageList;
    private static ScrollView messageScroll;
    private static TextView titleView;
    private static TextView statusView;
    private static TextView phoneStateView;
    private static EditText composerInput;
    private static Button sendButton;
    private static boolean agentBusy;
    private static boolean stopRequested;
    private static String screen = "";
    private static String currentSessionId = "";
    private static String currentSessionTitle = "定时任务";
    private static boolean changingPhone;

    private NativeUi() {}

    private static int dp(Context context, float value) {
        return Math.round(context.getResources().getDisplayMetrics().density * value);
    }

    private static GradientDrawable shape(int color, int radius, int border) {
        GradientDrawable result = new GradientDrawable();
        result.setColor(color);
        result.setCornerRadius(radius);
        if (border != Color.TRANSPARENT) result.setStroke(Math.max(1, radius / 18), border);
        return result;
    }

    private static GradientDrawable gradient(int start, int end, int radius, int border) {
        GradientDrawable result = new GradientDrawable(
            GradientDrawable.Orientation.TL_BR, new int[]{start, end});
        result.setCornerRadius(radius);
        if (border != Color.TRANSPARENT) result.setStroke(Math.max(1, radius / 18), border);
        return result;
    }

    private static Drawable glass(Context context, int radius) {
        return gradient(Color.argb(244, 255, 255, 255), GLASS,
                        dp(context, radius), Color.argb(210, 255, 255, 255));
    }

    private static void surface(View view, Drawable background, int elevation) {
        view.setBackground(background);
        view.setElevation(dp(view.getContext(), elevation));
    }

    private static void touch(View view, Drawable background) {
        view.setBackground(new RippleDrawable(
            ColorStateList.valueOf(Color.argb(38, 90, 90, 90)), background, null));
    }

    private static GradientDrawable orb(int color, int alpha) {
        GradientDrawable result = new GradientDrawable();
        result.setShape(GradientDrawable.OVAL);
        result.setColor(Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color)));
        return result;
    }

    private static LinearLayout column(Context context) {
        LinearLayout result = new LinearLayout(context);
        result.setOrientation(LinearLayout.VERTICAL);
        return result;
    }

    private static LinearLayout row(Context context) {
        LinearLayout result = new LinearLayout(context);
        result.setOrientation(LinearLayout.HORIZONTAL);
        result.setGravity(Gravity.CENTER_VERTICAL);
        return result;
    }

    private static TextView text(Context context, String value, int size, int color, boolean bold) {
        TextView result = new TextView(context);
        result.setText(value);
        result.setTextColor(color);
        result.setTextSize(size);
        if (bold) result.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        result.setIncludeFontPadding(false);
        result.setLineSpacing(dp(context, 2), 1.0f);
        result.setGravity(Gravity.CENTER_VERTICAL);
        return result;
    }

    private static TextView eyebrow(Context context, String value, int color) {
        TextView result = text(context, value, 11, color, true);
        result.setLetterSpacing(0.13f);
        return result;
    }

    private static Button button(Context context, String value, boolean filled) {
        Button result = new Button(context);
        result.setText(value);
        result.setTextSize(14);
        result.setAllCaps(false);
        result.setTextColor(filled ? WHITE : TEAL);
        result.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        if (filled) result.setBackground(filledButtonBackground(context));
        else touch(result, glass(context, 15));
        result.setMinHeight(dp(context, 48));
        result.setMinWidth(dp(context, 48));
        result.setPadding(dp(context, 12), 0, dp(context, 12), 0);
        return result;
    }

    static Drawable filledButtonBackground(Context context) {
        GradientDrawable fill = gradient(Color.rgb(129, 164, 222),
            Color.rgb(170, 151, 215), dp(context, 15), Color.TRANSPARENT);
        return new RippleDrawable(ColorStateList.valueOf(Color.argb(38, 90, 90, 90)), fill, null);
    }

    private static HeaderIconView headerIcon(Context context, boolean back) {
        HeaderIconView result = new HeaderIconView(context, back);
        result.setBackgroundColor(Color.TRANSPARENT);
        result.setClickable(true);
        result.setFocusable(true);
        return result;
    }

    private static final class HeaderIconView extends View {
        private final boolean back;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        HeaderIconView(Context context, boolean back) {
            super(context);
            this.back = back;
            paint.setColor(INK);
            paint.setStrokeCap(Paint.Cap.SQUARE);
            paint.setStyle(Paint.Style.STROKE);
        }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float density = getResources().getDisplayMetrics().density;
            float centerX = back ? getWidth() * 0.5f : getWidth() * 0.58f;
            float centerY = getHeight() * 0.5f;
            paint.setStrokeWidth(Math.max(1.5f, 1.8f * density));
            if (back) {
                float left = getWidth() * 0.30f;
                float right = getWidth() * 0.61f;
                float tip = getWidth() * 0.27f;
                float wing = getHeight() * 0.14f;
                canvas.drawLine(left, centerY, right, centerY, paint);
                canvas.drawLine(tip, centerY, left + wing, centerY - wing, paint);
                canvas.drawLine(tip, centerY, left + wing, centerY + wing, paint);
            } else {
                paint.setStyle(Paint.Style.FILL);
                float radius = Math.max(1.6f, 1.7f * density);
                float top = getHeight() * 0.35f;
                float gap = getHeight() * 0.16f;
                canvas.drawCircle(centerX, top, radius, paint);
                canvas.drawCircle(centerX, top + gap, radius, paint);
                canvas.drawCircle(centerX, top + gap * 2f, radius, paint);
            }
        }
    }

    private static LinearLayout.LayoutParams margins(Context context, int width, int height,
                                                      int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams result = new LinearLayout.LayoutParams(width, height);
        result.setMargins(dp(context, left), dp(context, top), dp(context, right), dp(context, bottom));
        return result;
    }

    private static void onMain(Activity activity, Runnable action) {
        if (Looper.myLooper() == Looper.getMainLooper()) action.run();
        else activity.runOnUiThread(action);
    }

    private static void ensure(Activity activity) {
        if (owner == activity && host != null && host.getParent() != null) return;
        owner = activity;
        ViewGroup content = activity.findViewById(android.R.id.content);
        if (content == null) throw new IllegalStateException("Android content view is unavailable");
        host = new FrameLayout(activity);
        host.setBackgroundColor(CANVAS);
        content.addView(host, new ViewGroup.LayoutParams(-1, -1));
        activity.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        if (activity instanceof AppCompatActivity) {
            androidx.appcompat.app.ActionBar bar = ((AppCompatActivity) activity).getSupportActionBar();
            if (bar != null) bar.hide();
            ((AppCompatActivity) activity).getOnBackPressedDispatcher().addCallback(
                (AppCompatActivity) activity, new OnBackPressedCallback(true) {
                    @Override public void handleOnBackPressed() {
                        if (screen.equals("sessions")) activity.finish();
                        else dispatch(screen.equals("task_add") ? "tasks" : "sessions", new JSONObject());
                    }
                });
        }
    }

    private static boolean dispatch(String action, JSONObject data) {
        try {
            Log.i(TAG, "action=" + action);
            PyObject result = Python.getInstance().getModule("muselite_py.native_ui_callbacks")
                .callAttr("on_action", action, data.toString());
            return result != null && result.toBoolean();
        } catch (Exception error) {
            Log.e(TAG, "action failed: " + action, error);
            status("界面操作失败：" + error.getMessage(), true);
            return false;
        }
    }

    public static void show(Activity activity, String stateJson) {
        onMain(activity, () -> {
            try {
                ensure(activity);
                JSONObject state = new JSONObject(stateJson);
                screen = state.optString("view", "sessions");
                NativeBridge.onScreenChanged(screen.equals("chat"));
                currentSessionId = state.optString("session_id", "");
                currentSessionTitle = state.optString("title", "定时任务");
                host.removeAllViews();
                page = column(activity);
                page.setBackgroundColor(screen.equals("chat") ? WHITE : Color.TRANSPARENT);
                host.addView(page, new FrameLayout.LayoutParams(-1, -1));
                messageList = null;
                messageScroll = null;
                statusView = null;
                phoneStateView = null;
                composerInput = null;
                sendButton = null;
                Log.i(TAG, "screen=" + screen);
                header(activity, state);
                if (screen.equals("chat")) chat(activity, state);
                else if (screen.equals("settings")) settings(activity, state);
                else if (screen.equals("tasks")) tasks(activity, state);
                else if (screen.equals("task_add")) taskAdd(activity);
                else sessions(activity, state);
            } catch (Exception error) {
                Log.e(TAG, "screen failed", error);
                if (host != null) {
                    host.removeAllViews();
                    TextView failure = text(activity, "界面加载失败：" + error.getMessage(), 16, RED, false);
                    failure.setPadding(dp(activity, 20), dp(activity, 20),
                                       dp(activity, 20), dp(activity, 20));
                    host.addView(failure, new FrameLayout.LayoutParams(-1, -2));
                }
            }
        });
    }

    private static void header(Activity activity, JSONObject state) {
        LinearLayout bar = row(activity);
        bar.setPadding(dp(activity, 18), dp(activity, 13), dp(activity, 18), dp(activity, 13));
        bar.setBackgroundColor(screen.equals("chat") ? WHITE : CANVAS);
        bar.setElevation(dp(activity, 3));
        if (!screen.equals("sessions")) {
            HeaderIconView back = headerIcon(activity, true);
            back.setContentDescription("返回上一页");
            back.setOnClickListener(view -> dispatch(screen.equals("task_add") ? "tasks" : "sessions", new JSONObject()));
            bar.addView(back, new LinearLayout.LayoutParams(dp(activity, 48), dp(activity, 48)));
        } else {
            TextView mark = text(activity, "✦", 24, TEAL, true);
            mark.setGravity(Gravity.CENTER);
            mark.setBackground(shape(Color.rgb(235, 240, 250), dp(activity, 16),
                                     Color.rgb(211, 222, 243)));
            mark.setContentDescription("MuseLite");
            bar.addView(mark, new LinearLayout.LayoutParams(dp(activity, 48), dp(activity, 48)));
        }
        LinearLayout titles = column(activity);
        String title = state.optString("title", "MuseLite");
        titleView = text(activity, title, 17, INK, true);
        titleView.setSingleLine(true);
        titleView.setEllipsize(android.text.TextUtils.TruncateAt.END);
        titles.addView(titleView);
        String subtext = state.optString("subtitle", "Python Agent");
        if (screen.equals("sessions")) {
            try {
                String version = activity.getPackageManager()
                    .getPackageInfo(activity.getPackageName(), 0).versionName;
                subtext += " · v" + version;
            } catch (Exception ignored) {}
        }
        TextView subtitle = text(activity, subtext, 10, MUTED, false);
        subtitle.setSingleLine(true);
        subtitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        titles.addView(subtitle);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, -2, 1);
        titleParams.leftMargin = dp(activity, 13);
        titleParams.rightMargin = dp(activity, 8);
        bar.addView(titles, titleParams);
        if (screen.equals("chat") || screen.equals("sessions")) {
            HeaderIconView settings = headerIcon(activity, false);
            settings.setContentDescription("打开设置");
            settings.setOnClickListener(view -> dispatch("settings", new JSONObject()));
            bar.addView(settings, new LinearLayout.LayoutParams(dp(activity, 48), dp(activity, 48)));
        }
        page.addView(bar, new LinearLayout.LayoutParams(-1, -2));
    }

    private static void sessions(Activity activity, JSONObject state) {
        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout body = column(activity);
        body.setPadding(dp(activity, 18), dp(activity, 22), dp(activity, 18), dp(activity, 28));
        scroll.addView(body);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        FrameLayout hero = new FrameLayout(activity);
        surface(hero, gradient(Color.rgb(255, 255, 255), Color.rgb(247, 248, 255),
                               dp(activity, 26), Color.rgb(255, 255, 255)), 3);
        hero.setClipToOutline(true);
        View glow = new View(activity);
        glow.setBackground(orb(MINT, 46));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            glow.setRenderEffect(RenderEffect.createBlurEffect(
                dp(activity, 28), dp(activity, 28), Shader.TileMode.CLAMP));
        }
        FrameLayout.LayoutParams glowParams = new FrameLayout.LayoutParams(dp(activity, 168), dp(activity, 168));
        glowParams.gravity = Gravity.TOP | Gravity.RIGHT;
        glowParams.setMargins(0, dp(activity, -48), dp(activity, -38), 0);
        hero.addView(glow, glowParams);
        View glowSmall = new View(activity);
        glowSmall.setBackground(orb(WHITE, 23));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            glowSmall.setRenderEffect(RenderEffect.createBlurEffect(
                dp(activity, 17), dp(activity, 17), Shader.TileMode.CLAMP));
        }
        FrameLayout.LayoutParams smallParams = new FrameLayout.LayoutParams(dp(activity, 96), dp(activity, 96));
        smallParams.gravity = Gravity.BOTTOM | Gravity.RIGHT;
        smallParams.setMargins(0, 0, dp(activity, 83), dp(activity, -45));
        hero.addView(glowSmall, smallParams);
        LinearLayout heroContent = column(activity);
        heroContent.setPadding(dp(activity, 22), dp(activity, 23), dp(activity, 22), dp(activity, 25));
        heroContent.addView(eyebrow(activity, "MUSELITE  /  AI WORKSPACE", TEAL));
        TextView headline = text(activity, "从一个想法，\n走向下一步。", 25, INK, true);
        headline.setLineSpacing(dp(activity, 4), 1.0f);
        heroContent.addView(headline, margins(activity, -1, -2, 0, 13, 0, 0));
        TextView description = text(activity, "随时提问、整理思路，或交给 Agent 处理。", 13,
                                    MUTED, false);
        heroContent.addView(description, margins(activity, -1, -2, 0, 13, 12, 0));
        hero.addView(heroContent, new FrameLayout.LayoutParams(-1, -2));
        body.addView(hero, margins(activity, -1, -2, 0, 0, 0, 0));

        Button create = button(activity, "定时任务", true);
        create.setContentDescription("定时任务");
        create.setOnClickListener(view -> dispatch("tasks", new JSONObject()));
        create.setElevation(dp(activity, 3));
        body.addView(create, margins(activity, -1, dp(activity, 54), 0, 21, 0, 27));
        LinearLayout section = row(activity);
        section.addView(text(activity, "最近对话", 18, INK, true),
                        new LinearLayout.LayoutParams(0, -2, 1));
        JSONArray sessions = state.optJSONArray("sessions");
        TextView count = text(activity, (sessions == null ? 0 : sessions.length()) + " 个会话",
                              11, TEAL, true);
        count.setPadding(dp(activity, 10), dp(activity, 5), dp(activity, 10), dp(activity, 5));
        count.setBackground(shape(Color.rgb(235, 237, 252), dp(activity, 20),
                                  Color.TRANSPARENT));
        section.addView(count);
        body.addView(section, margins(activity, -1, -2, 2, 0, 2, 13));
        if (sessions == null || sessions.length() == 0) {
            LinearLayout empty = column(activity);
            empty.setPadding(dp(activity, 20), dp(activity, 22), dp(activity, 20), dp(activity, 23));
            surface(empty, glass(activity, 20), 2);
            empty.addView(text(activity, "这里会收藏你的每一次探索", 15, INK, true));
            empty.addView(text(activity, "在下方输入消息，第一段对话就会出现在这里。",
                               12, MUTED, false), margins(activity, -1, -2, 0, 8, 0, 0));
            body.addView(empty, new LinearLayout.LayoutParams(-1, -2));
        } else {
            for (int i = 0; i < sessions.length(); i++) {
                JSONObject session = sessions.optJSONObject(i);
                if (session == null) continue;
                String id = session.optString("id", "");
                LinearLayout card = row(activity);
                card.setPadding(dp(activity, 14), dp(activity, 14), dp(activity, 14), dp(activity, 14));
                touch(card, glass(activity, 19));
                card.setElevation(dp(activity, 2));
                TextView symbol = text(activity, "✦", 20, TEAL, true);
                symbol.setGravity(Gravity.CENTER);
                symbol.setBackground(shape(Color.rgb(226, 245, 255), dp(activity, 13),
                                           Color.TRANSPARENT));
                card.addView(symbol, new LinearLayout.LayoutParams(dp(activity, 42), dp(activity, 42)));
                LinearLayout details = column(activity);
                TextView sessionTitle = text(activity, session.optString("title", "新对话"), 15, INK, true);
                sessionTitle.setMaxLines(2);
                sessionTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
                details.addView(sessionTitle);
                details.addView(text(activity, session.optString("updated", ""), 11, MUTED, false),
                                margins(activity, -1, -2, 0, 5, 0, 0));
                LinearLayout.LayoutParams detailsParams = new LinearLayout.LayoutParams(0, -2, 1);
                detailsParams.leftMargin = dp(activity, 13);
                card.addView(details, detailsParams);
                card.addView(text(activity, "›", 24, MUTED, false),
                             margins(activity, -2, -2, 7, 0, 2, 0));
                card.setClickable(true);
                card.setFocusable(true);
                card.setContentDescription("打开会话：" + session.optString("title", "新对话"));
                card.setOnClickListener(view -> {
                    JSONObject data = new JSONObject();
                    try { data.put("id", id); } catch (JSONException ignored) {}
                    dispatch("open", data);
                });
                body.addView(card, margins(activity, -1, -2, 0, 0, 0, 11));
            }
        }
        composer(activity, "直接输入消息，开始新对话…", "start", state);
    }

    private static void tasks(Activity activity, JSONObject state) {
        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        LinearLayout body = column(activity);
        body.setPadding(dp(activity, 18), dp(activity, 22), dp(activity, 18), dp(activity, 28));
        statusView = text(activity, "", 12, RED, false);
        body.addView(statusView);
        scroll.addView(body);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        JSONArray items = state.optJSONArray("tasks");
        if (items == null || items.length() == 0) {
            LinearLayout empty = column(activity);
            empty.setPadding(dp(activity, 20), dp(activity, 22), dp(activity, 20), dp(activity, 22));
            surface(empty, glass(activity, 18), 2);
            empty.addView(text(activity, "还没有定时任务", 16, INK, true));
            empty.addView(text(activity, "点击右下角加号创建一个自动执行的 Prompt。", 12, MUTED, false));
            body.addView(empty);
        } else {
            for (int i = 0; i < items.length(); i++) {
                JSONObject task = items.optJSONObject(i);
                if (task == null) continue;
                String id = task.optString("id", "");
                LinearLayout card = column(activity);
                card.setPadding(dp(activity, 15), dp(activity, 13), dp(activity, 12), dp(activity, 13));
                surface(card, glass(activity, 16), 2);
                LinearLayout line = row(activity);
                line.addView(text(activity, task.optString("name", "定时任务"), 16, INK, true),
                             new LinearLayout.LayoutParams(0, -2, 1));
                CheckBox enabled = new CheckBox(activity);
                enabled.setChecked(task.optInt("enabled", 0) != 0);
                enabled.setButtonTintList(ColorStateList.valueOf(TEAL));
                enabled.setContentDescription("启用任务");
                enabled.setOnCheckedChangeListener((button, checked) -> {
                    JSONObject data = new JSONObject();
                    try { data.put("id", id); data.put("enabled", checked); } catch (JSONException ignored) {}
                    dispatch("task_toggle", data);
                });
                line.addView(enabled, new LinearLayout.LayoutParams(dp(activity, 50), dp(activity, 48)));
                Button delete = button(activity, "删除", false);
                delete.setTextColor(RED);
                delete.setOnClickListener(view -> {
                    JSONObject data = new JSONObject();
                    try { data.put("id", id); } catch (JSONException ignored) {}
                    dispatch("task_delete", data);
                });
                line.addView(delete, new LinearLayout.LayoutParams(dp(activity, 60), dp(activity, 46)));
                card.addView(line);
                String frequency = task.optInt("repeat_daily", 0) != 0 ? "每天重复" : "一次性";
                card.addView(text(activity, frequency + " · " + task.optString("time_label", ""),
                                  12, MUTED, false), margins(activity, -1, -2, 0, 4, 0, 0));
                card.addView(text(activity, task.optString("prompt", ""), 13, INK, false),
                             margins(activity, -1, -2, 0, 7, 0, 0));
                body.addView(card, margins(activity, -1, -2, 0, 0, 0, 11));
            }
        }
        Button add = button(activity, "+", true);
        add.setTextSize(28);
        add.setContentDescription("添加定时任务");
        add.setOnClickListener(view -> dispatch("task_add", new JSONObject()));
        FrameLayout.LayoutParams addParams = new FrameLayout.LayoutParams(dp(activity, 58), dp(activity, 58));
        addParams.gravity = Gravity.BOTTOM | Gravity.RIGHT;
        addParams.setMargins(0, 0, dp(activity, 20), dp(activity, 22));
        host.addView(add, addParams);
    }

    private static void taskAdd(Activity activity) {
        LinearLayout body = column(activity);
        body.setPadding(dp(activity, 18), dp(activity, 22), dp(activity, 18), dp(activity, 26));
        page.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
        statusView = text(activity, "", 12, RED, false);
        body.addView(statusView);
        EditText name = new EditText(activity); name.setHint("任务名称"); name.setTextSize(15);
        body.addView(name, margins(activity, -1, dp(activity, 58), 0, 0, 0, 12));
        EditText prompt = new EditText(activity); prompt.setHint("任务要求 / Prompt"); prompt.setTextSize(15);
        prompt.setGravity(Gravity.TOP); prompt.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        body.addView(prompt, margins(activity, -1, dp(activity, 130), 0, 0, 0, 16));
        final boolean[] daily = {false};
        final boolean[] timeSelected = {false};
        final Calendar selected = Calendar.getInstance();
        Button when = button(activity, "选择时间", false);
        Button frequency = button(activity, "频率：一次性", false);
        frequency.setOnClickListener(view -> {
            daily[0] = !daily[0];
            frequency.setText(daily[0] ? "频率：每天重复" : "频率：一次性");
            if (timeSelected[0]) when.setText(daily[0]
                ? String.format("每天 %02d:%02d", selected.get(Calendar.HOUR_OF_DAY), selected.get(Calendar.MINUTE))
                : String.format("时间：%04d-%02d-%02d %02d:%02d",
                    selected.get(Calendar.YEAR), selected.get(Calendar.MONTH) + 1,
                    selected.get(Calendar.DAY_OF_MONTH), selected.get(Calendar.HOUR_OF_DAY),
                    selected.get(Calendar.MINUTE)));
        });
        body.addView(frequency, margins(activity, -1, dp(activity, 50), 0, 0, 0, 10));
        when.setOnClickListener(view -> {
            if (daily[0]) {
                showTaskTimePicker(activity, selected, when, timeSelected, true);
            } else {
                DatePickerDialog date = new DatePickerDialog(activity, (v, year, month, day) -> {
                    selected.set(year, month, day);
                    showTaskTimePicker(activity, selected, when, timeSelected, false);
                }, selected.get(Calendar.YEAR), selected.get(Calendar.MONTH), selected.get(Calendar.DAY_OF_MONTH));
                date.show();
            }
        });
        body.addView(when, margins(activity, -1, dp(activity, 50), 0, 0, 0, 22));
        Button save = button(activity, "保存任务", true);
        save.setOnClickListener(view -> {
            String taskName = name.getText().toString().trim(), taskPrompt = prompt.getText().toString().trim();
            if (taskName.isEmpty() || taskPrompt.isEmpty()) { status("请填写任务名称和任务要求", true); return; }
            if (!timeSelected[0]) { status("请选择执行时间", true); return; }
            JSONObject data = new JSONObject();
            try { data.put("name", taskName); data.put("prompt", taskPrompt); data.put("when_ms", selected.getTimeInMillis()); data.put("repeat_daily", daily[0]); }
            catch (JSONException ignored) {}
            dispatch("task_save", data);
        });
        body.addView(save, new LinearLayout.LayoutParams(-1, dp(activity, 52)));
    }

    private static void showTaskTimePicker(Activity activity, Calendar selected, Button when,
                                           boolean[] timeSelected, boolean daily) {
        new TimePickerDialog(activity, (view, hour, minute) -> {
            selected.set(Calendar.HOUR_OF_DAY, hour); selected.set(Calendar.MINUTE, minute);
            selected.set(Calendar.SECOND, 0); selected.set(Calendar.MILLISECOND, 0);
            timeSelected[0] = true;
            when.setText(daily ? String.format("每天 %02d:%02d", hour, minute)
                : String.format("时间：%04d-%02d-%02d %02d:%02d",
                    selected.get(Calendar.YEAR), selected.get(Calendar.MONTH) + 1,
                    selected.get(Calendar.DAY_OF_MONTH), hour, minute));
        }, selected.get(Calendar.HOUR_OF_DAY), selected.get(Calendar.MINUTE), true).show();
    }

    private static void chooseScheduleMode(Activity activity, String sessionId, String title,
                                           String prompt) {
        new AlertDialog.Builder(activity).setTitle("定时启动方式")
            .setItems(new String[]{"一次性", "每天重复"}, (dialog, which) ->
                scheduleSession(activity, sessionId, title, prompt, which == 1)).show();
    }

    private static void scheduleSession(Activity activity, String sessionId, String title,
                                        String prompt, boolean repeatDaily) {
        prompt = prompt == null ? "" : prompt.trim();
        if (prompt.isEmpty()) {
            status("请先在输入框中填写要定时发送的指令", true);
            return;
        }
        final String scheduledPrompt = prompt;
        Calendar now = Calendar.getInstance();
        DatePickerDialog date = new DatePickerDialog(activity, (view, year, month, day) -> {
            TimePickerDialog time = new TimePickerDialog(activity, (timeView, hour, minute) -> {
                Calendar when = Calendar.getInstance();
                when.set(year, month, day, hour, minute, 0);
                when.set(Calendar.MILLISECOND, 0);
                try {
                    SessionAlarmScheduler.schedule(activity, sessionId, scheduledPrompt,
                                                   when.getTimeInMillis(), repeatDaily);
                    JSONObject rename = new JSONObject();
                    rename.put("id", sessionId);
                    rename.put("title", "定时任务");
                    dispatch("rename", rename);
                    status("已设置“定时任务”于 " + String.format("%04d-%02d-%02d %02d:%02d", year, month + 1, day, hour, minute) + (repeatDaily ? " 每天发送" : " 发送"), false);
                    dispatch("sessions", new JSONObject());
                } catch (Exception error) { status("定时设置失败：" + error.getMessage(), true); }
            }, now.get(Calendar.HOUR_OF_DAY), now.get(Calendar.MINUTE), true);
            time.setTitle("选择启动时间"); time.show();
        }, now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH));
        date.setTitle("选择启动日期"); date.show();
    }

    private static void chat(Activity activity, JSONObject state) {
        messageScroll = new ScrollView(activity);
        messageScroll.setBackgroundColor(WHITE);
        messageScroll.setFillViewport(true);
        messageScroll.setVerticalScrollBarEnabled(false);
        messageList = column(activity);
        messageList.setBackgroundColor(WHITE);
        messageList.setPadding(dp(activity, 18), dp(activity, 22), dp(activity, 18), dp(activity, 22));
        messageScroll.addView(messageList);
        page.addView(messageScroll, new LinearLayout.LayoutParams(-1, 0, 1));
        renderMessages(activity, state.optJSONArray("messages"));
        composer(activity, "输入消息，继续对话…", "send", state);
        busy(state.optBoolean("busy", false));
    }

    private static void composer(Activity activity, String hint, String action, JSONObject state) {
        LinearLayout outer = column(activity);
        outer.setPadding(dp(activity, 16), dp(activity, 12), dp(activity, 16), dp(activity, 12));
        GradientDrawable composerGlass = gradient(Color.WHITE, Color.WHITE, 0, Color.rgb(218, 232, 255));
        float curve = dp(activity, 23);
        composerGlass.setCornerRadii(new float[]{curve, curve, curve, curve, 0, 0, 0, 0});
        surface(outer, composerGlass, 12);
        statusView = text(activity, "", 12, MUTED, false);
        statusView.setPadding(dp(activity, 10), dp(activity, 6),
                              dp(activity, 10), dp(activity, 6));
        outer.addView(statusView, margins(activity, -1, -2, 0, 0, 0, 8));
        if (screen.equals("chat")) {
            statusView.addOnLayoutChangeListener((view, left, top, right, bottom,
                                                  oldLeft, oldTop, oldRight, oldBottom) ->
                NativeBridge.positionPreview(activity));
        }
        status(state.optString("status", ""), state.optBoolean("status_error", false));

        LinearLayout inputRow = row(activity);
        composerInput = new EditText(activity);
        composerInput.setTextSize(15);
        composerInput.setTextColor(INK);
        composerInput.setHintTextColor(MUTED);
        composerInput.setHint(hint);
        composerInput.setMinLines(1);
        composerInput.setMaxLines(4);
        composerInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE |
                                   InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        composerInput.setMinHeight(dp(activity, 50));
        composerInput.setPadding(dp(activity, 15), dp(activity, 10),
                                 dp(activity, 15), dp(activity, 10));
        composerInput.setBackground(shape(Color.rgb(247, 248, 255), dp(activity, 17), LINE));
        inputRow.addView(composerInput, new LinearLayout.LayoutParams(0, -2, 1));
        sendButton = button(activity, "发送", true);
        sendButton.setContentDescription("发送消息");
        sendButton.setOnClickListener(view -> {
            if (screen.equals("chat") && agentBusy) {
                if (!stopRequested) {
                    stopRequested = true;
                    sendButton.setText("停止中");
                    sendButton.setEnabled(false);
                    dispatch("stop", new JSONObject());
                }
                return;
            }
            String prompt = composerInput.getText().toString().trim();
            if (prompt.isEmpty()) { status("请先输入消息", true); return; }
            JSONObject data = new JSONObject();
            try { data.put("text", prompt); } catch (JSONException ignored) {}
            if (dispatch(action, data)) composerInput.setText("");
        });
        inputRow.addView(sendButton, margins(activity, dp(activity, 82), dp(activity, 50), 9, 0, 0, 0));
        outer.addView(inputRow, new LinearLayout.LayoutParams(-1, -2));
        page.addView(outer, new LinearLayout.LayoutParams(-1, -2));
        if (screen.equals("chat")) {
            page.addOnLayoutChangeListener((view, left, top, right, bottom,
                                            oldLeft, oldTop, oldRight, oldBottom) ->
                NativeBridge.positionPreview(activity));
            composerInput.addOnLayoutChangeListener((view, left, top, right, bottom,
                                                     oldLeft, oldTop, oldRight, oldBottom) ->
                NativeBridge.positionPreview(activity));
        }
    }

    static int composerInputTopOnScreen(Activity activity) {
        if (owner != activity || !screen.equals("chat") || composerInput == null ||
                !composerInput.isAttachedToWindow() || composerInput.getHeight() <= 0) return -1;
        int[] location = new int[2];
        composerInput.getLocationOnScreen(location);
        return location[1];
    }

    static boolean isChatScreen(Activity activity) {
        return owner == activity && screen.equals("chat");
    }

    static int previewAnchorTopOnScreen(Activity activity) {
        if (isChatScreen(activity) && statusView != null &&
                statusView.getVisibility() == View.VISIBLE &&
                statusView.isAttachedToWindow() && statusView.getHeight() > 0) {
            int[] location = new int[2];
            statusView.getLocationOnScreen(location);
            return location[1];
        }
        return composerInputTopOnScreen(activity);
    }

    private static void renderMessages(Activity activity, JSONArray messages) {
        if (messageList == null || messageScroll == null) return;
        boolean nearBottom = messageScroll.getHeight() == 0 ||
            messageScroll.getScrollY() + messageScroll.getHeight() >=
                messageList.getHeight() - dp(activity, 150);
        messageList.removeAllViews();
        if (messages == null || messages.length() == 0) {
            messageList.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout welcomeCard = column(activity);
            welcomeCard.setPadding(dp(activity, 24), dp(activity, 30),
                                   dp(activity, 24), dp(activity, 31));
            surface(welcomeCard, glass(activity, 24), 3);
            TextView mark = text(activity, "✦", 30, TEAL, true);
            mark.setGravity(Gravity.CENTER);
            mark.setBackground(shape(Color.rgb(235, 241, 253), dp(activity, 21),
                                     Color.argb(155, 255, 255, 255)));
            LinearLayout.LayoutParams markParams = new LinearLayout.LayoutParams(
                dp(activity, 62), dp(activity, 62));
            markParams.gravity = Gravity.CENTER_HORIZONTAL;
            welcomeCard.addView(mark, markParams);
            TextView welcome = text(activity, "有什么可以帮你？", 22, INK, true);
            welcome.setGravity(Gravity.CENTER);
            welcomeCard.addView(welcome, margins(activity, -1, -2, 0, 17, 0, 0));
            TextView hint = text(activity, "输入问题或任务，MuseLite 会在这里回应你。", 13, MUTED, false);
            hint.setGravity(Gravity.CENTER);
            welcomeCard.addView(hint, margins(activity, -1, -2, 0, 9, 0, 0));
            messageList.addView(welcomeCard, new LinearLayout.LayoutParams(-1, -2));
            return;
        }
        messageList.setGravity(Gravity.TOP);
        int first = Math.max(0, messages.length() - 80);
        for (int i = first; i < messages.length(); i++) {
            JSONObject message = messages.optJSONObject(i);
            if (message == null) continue;
            String role = message.optString("role", "assistant");
            String content = message.optString("content", "");
            if (content.isEmpty() && !message.optBoolean("pending", false)) continue;
            boolean user = role.equals("user");
            boolean error = role.equals("error");
            boolean tool = role.equals("tool");
            String speaker = user ? "USER" : tool ? message.optString("name", "工具")
                            : error ? "错误" : role.equals("status") ? "状态" : "MUSELITE";
            LinearLayout card = column(activity);
            card.setPadding(dp(activity, 16), dp(activity, 13), dp(activity, 16), dp(activity, 15));
            Drawable cardBackground = user
                ? gradient(DEEP, Color.rgb(121, 163, 222), dp(activity, 19), Color.TRANSPARENT)
                : error ? shape(Color.rgb(255, 241, 237), dp(activity, 19),
                                Color.rgb(246, 211, 204))
                : tool ? gradient(Color.argb(246, 236, 240, 255),
                                  Color.argb(235, 246, 242, 255), dp(activity, 19), LINE)
                : glass(activity, 19);
            surface(card, cardBackground, user ? 3 : 2);
            TextView who = eyebrow(activity, speaker,
                                   user ? Color.rgb(255, 255, 255) : error ? RED : TEAL);
            card.addView(who);
            TextView body = text(activity, content.isEmpty() ? "正在回复…" : content,
                                 15, user ? WHITE : error ? RED : INK, false);
            body.setLineSpacing(dp(activity, 4), 1.0f);
            if (tool) {
                body.setTypeface(Typeface.MONOSPACE);
                body.setTextSize(12);
            }
            body.setTextIsSelectable(true);
            if (role.equals("assistant") && !content.isEmpty()) {
                try {
                    body.setText(Html.fromHtml(message.optString("html", content),
                                               Html.FROM_HTML_MODE_COMPACT));
                } catch (Exception ignored) { body.setText(content); }
            }
            card.addView(body, margins(activity, -1, -2, 0, 9, 0, 0));
            LinearLayout.LayoutParams cardParams = margins(activity, -1, -2,
                                                           user ? 34 : 0, 0, user ? 0 : 34, 13);
            messageList.addView(card, cardParams);
        }
        if (nearBottom) messageScroll.post(() -> messageScroll.fullScroll(View.FOCUS_DOWN));
    }

    private static EditText field(Activity activity, LinearLayout body, String title,
                                  String value, boolean secret) {
        body.addView(text(activity, title, 12, MUTED, true),
                     margins(activity, -1, -2, 2, 18, 0, 8));
        EditText input = new EditText(activity);
        input.setText(value);
        input.setTextSize(15);
        input.setTextColor(INK);
        input.setHintTextColor(MUTED);
        if (secret) input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        input.setSingleLine(true);
        input.setPadding(dp(activity, 15), 0, dp(activity, 15), 0);
        input.setBackground(shape(Color.rgb(247, 248, 255), dp(activity, 14), LINE));
        body.addView(input, new LinearLayout.LayoutParams(-1, dp(activity, 52)));
        return input;
    }

    private static void settings(Activity activity, JSONObject state) {
        statusView = text(activity, "", 12, MUTED, false);
        statusView.setPadding(dp(activity, 12), dp(activity, 10),
                              dp(activity, 12), dp(activity, 10));
        page.addView(statusView, margins(activity, -1, -2, 18, 12, 18, 0));
        status(state.optString("status", ""), state.optBoolean("status_error", false));

        ScrollView scroll = new ScrollView(activity);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout body = column(activity);
        body.setPadding(dp(activity, 18), dp(activity, 22), dp(activity, 18), dp(activity, 32));
        scroll.addView(body);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        body.addView(text(activity, "让 MuseLite 更懂你的任务", 22, INK, true));
        body.addView(text(activity, "连接模型，并按需启用手机操作。", 13, MUTED, false),
                     margins(activity, -1, -2, 0, 7, 0, 20));

        LinearLayout modelCard = column(activity);
        modelCard.setPadding(dp(activity, 19), dp(activity, 20), dp(activity, 19), dp(activity, 21));
        surface(modelCard, glass(activity, 22), 3);
        modelCard.addView(eyebrow(activity, "01  /  MODEL CONNECTION", TEAL));
        modelCard.addView(text(activity, "模型连接", 18, INK, true),
                          margins(activity, -1, -2, 0, 10, 0, 0));
        EditText base = field(activity, modelCard, "API 基础 URL", state.optString("base_url", ""), false);
        EditText model = field(activity, modelCard, "模型 ID", state.optString("model", ""), false);
        EditText key = field(activity, modelCard, "API Key", "", true);
        key.setHint("留空则保留现有密钥");
        modelCard.addView(text(activity, "密钥通过 Android Keystore 加密保存。", 11, MUTED, false),
                          margins(activity, -1, -2, 2, 9, 0, 0));
        CheckBox vision = new CheckBox(activity);
        vision.setText("模型支持截图图像输入");
        vision.setTextColor(INK);
        vision.setTextSize(13);
        vision.setButtonTintList(ColorStateList.valueOf(TEAL));
        vision.setChecked(state.optBoolean("vision", true));
        modelCard.addView(vision, margins(activity, -1, -2, 0, 14, 0, 0));
        Button save = button(activity, "保存模型设置", true);
        save.setOnClickListener(view -> {
            JSONObject data = new JSONObject();
            try {
                data.put("base_url", base.getText().toString());
                data.put("model", model.getText().toString());
                data.put("key", key.getText().toString());
                data.put("vision", vision.isChecked());
            } catch (JSONException ignored) {}
            if (dispatch("save_settings", data)) key.setText("");
        });
        modelCard.addView(save, margins(activity, -1, dp(activity, 50), 0, 16, 0, 0));
        TextView example = text(activity,
            "DeepSeek 示例  ·  https://api.deepseek.com  ·  deepseek-flash",
            11, MUTED, false);
        example.setPadding(dp(activity, 12), dp(activity, 9),
                           dp(activity, 12), dp(activity, 9));
        example.setBackground(shape(Color.rgb(239, 243, 253), dp(activity, 12),
                                    Color.TRANSPARENT));
        modelCard.addView(example, margins(activity, -1, -2, 0, 14, 0, 0));
        body.addView(modelCard, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout phoneCard = column(activity);
        phoneCard.setPadding(dp(activity, 19), dp(activity, 20), dp(activity, 19), dp(activity, 21));
        surface(phoneCard, glass(activity, 22), 3);
        phoneCard.addView(eyebrow(activity, "02  /  DEVICE ACCESS", TEAL));
        phoneCard.addView(text(activity, "手机操作", 18, INK, true),
                          margins(activity, -1, -2, 0, 10, 0, 0));
        phoneCard.addView(text(activity, "仅在你启用授权后，Agent 才能读取和操作屏幕。",
                                12, MUTED, false), margins(activity, -1, -2, 0, 8, 0, 0));
        JSONObject phone = state.optJSONObject("phone");
        if (phone == null) phone = new JSONObject();
        CheckBox enabled = new CheckBox(activity);
        enabled.setText("允许 Agent 操作手机");
        enabled.setTextColor(INK);
        enabled.setTextSize(14);
        enabled.setButtonTintList(ColorStateList.valueOf(TEAL));
        enabled.setChecked(phone.optBoolean("enabled", false));
        enabled.setOnCheckedChangeListener((button, checked) -> {
            if (changingPhone) return;
            JSONObject data = new JSONObject();
            try { data.put("enabled", checked); } catch (JSONException ignored) {}
            if (!dispatch("phone_toggle", data)) {
                changingPhone = true;
                button.setChecked(!checked);
                changingPhone = false;
            }
        });
        phoneCard.addView(enabled, margins(activity, -1, -2, 0, 15, 0, 0));
        phoneStateView = text(activity, "", 12, MUTED, false);
        phoneStateView.setPadding(dp(activity, 11), dp(activity, 9),
                                  dp(activity, 11), dp(activity, 9));
        phoneCard.addView(phoneStateView, margins(activity, -1, -2, 0, 9, 0, 12));
        phoneState(phone.toString());
        Button accessibility = button(activity, "打开系统无障碍设置", false);
        accessibility.setOnClickListener(view -> dispatch("accessibility", new JSONObject()));
        phoneCard.addView(accessibility, margins(activity, -1, dp(activity, 48), 0, 5, 0, 0));
        Button notifications = button(activity, "申请通知权限", false);
        notifications.setOnClickListener(view -> dispatch("notifications", new JSONObject()));
        phoneCard.addView(notifications, margins(activity, -1, dp(activity, 48), 0, 9, 0, 0));
        Button refresh = button(activity, "刷新授权状态", false);
        refresh.setOnClickListener(view -> dispatch("phone_refresh", new JSONObject()));
        phoneCard.addView(refresh, margins(activity, -1, dp(activity, 48), 0, 9, 0, 0));
        phoneCard.addView(text(activity,
            "启用手机操作需要系统无障碍授权；关闭开关会停止当前任务。",
            11, MUTED, false), margins(activity, -1, -2, 2, 13, 0, 0));
        body.addView(phoneCard, margins(activity, -1, -2, 0, 16, 0, 0));
    }

    public static void updateChat(Activity activity, String stateJson) {
        onMain(activity, () -> {
            if (!screen.equals("chat") || owner != activity) return;
            try {
                JSONObject state = new JSONObject(stateJson);
                String updatedSessionId = state.optString("session_id", "");
                if (!updatedSessionId.isEmpty()) currentSessionId = updatedSessionId;
                currentSessionTitle = state.optString("title", currentSessionTitle);
                if (titleView != null) titleView.setText(state.optString("title", "新对话"));
                renderMessages(activity, state.optJSONArray("messages"));
                busy(state.optBoolean("busy", false));
                status(state.optString("status", ""), state.optBoolean("status_error", false));
            } catch (JSONException error) { status("对话显示失败：" + error.getMessage(), true); }
        });
    }

    public static void busy(boolean value) {
        agentBusy = value;
        if (!value) stopRequested = false;
        if (sendButton != null && screen.equals("chat")) {
            sendButton.setText(value ? (stopRequested ? "停止中" : "停止") : "发送");
            sendButton.setContentDescription(value ? "中断智能体任务" : "发送消息");
            sendButton.setEnabled(!stopRequested);
            sendButton.setAlpha(stopRequested ? 0.48f : 1.0f);
        }
    }

    public static void status(String value, boolean error) {
        if (statusView == null) return;
        statusView.setText(value);
        statusView.setTextColor(error ? RED : TEAL);
        statusView.setBackground(shape(error ? Color.rgb(255, 239, 234)
                                        : Color.rgb(235, 241, 253),
                                       dp(statusView.getContext(), 11), Color.TRANSPARENT));
        statusView.setVisibility(value == null || value.isEmpty() ? View.GONE : View.VISIBLE);
    }

    public static void phoneState(String json) {
        if (phoneStateView == null) return;
        try {
            JSONObject value = new JSONObject(json);
            boolean service = value.optBoolean("service", false);
            boolean notifications = value.optBoolean("notifications", false);
            phoneStateView.setText("系统无障碍：" + (service ? "已启用" : "未启用") +
                                   "    通知：" + (notifications ? "已允许" : "未允许"));
            phoneStateView.setTextColor(service && notifications ? TEAL : RED);
            phoneStateView.setBackground(shape(service && notifications
                    ? Color.rgb(235, 241, 253) : Color.rgb(255, 243, 237),
                    dp(phoneStateView.getContext(), 12), Color.TRANSPARENT));
        } catch (JSONException error) { phoneStateView.setText("无法读取手机操作状态"); }
    }
}
