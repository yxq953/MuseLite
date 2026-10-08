package com.muselite.python;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.Html;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native Markdown blocks, with selectable text and scrollable wide content. */
public final class ReplyView {
    private static final int INK = Color.rgb(42, 55, 78);
    private static final int MUTED = Color.rgb(112, 124, 145);
    private ReplyView() {}

    private static int dp(Context c, int value) {
        return Math.round(value * c.getResources().getDisplayMetrics().density);
    }

    private static LinearLayout column(Context c) {
        LinearLayout box = new LinearLayout(c);
        box.setOrientation(LinearLayout.VERTICAL);
        return box;
    }

    private static TextView text(Context c, String value, int size, boolean markup) {
        TextView view = new TextView(c);
        view.setText(markup ? Html.fromHtml(value.replace("<code>", "<tt>")
                .replace("</code>", "</tt>"), Html.FROM_HTML_MODE_COMPACT) : value);
        view.setTextSize(size);
        view.setTextColor(INK);
        view.setIncludeFontPadding(false);
        view.setLineSpacing(dp(c, 3), 1.12f);
        view.setTextIsSelectable(true);
        return view;
    }

    private static GradientDrawable surface(Context c, int color) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(c, 10));
        return shape;
    }

    public static View render(Context c, JSONArray blocks) {
        LinearLayout content = column(c);
        for (int i = 0; i < blocks.length(); i++) {
            JSONObject block = blocks.optJSONObject(i);
            if (block == null) continue;
            String type = block.optString("type");
            View view;
            int top = 0;
            int bottom = 12;
            if (type.equals("code")) {
                view = code(c, block);
                top = 4;
            } else if (type.equals("table")) {
                view = table(c, block.optJSONArray("rows"));
                top = 4;
            } else if (type.equals("divider")) {
                view = new View(c);
                view.setBackgroundColor(Color.rgb(224, 229, 241));
                top = 8;
                bottom = 16;
            } else if (type.equals("list_item")) {
                LinearLayout line = new LinearLayout(c);
                line.setOrientation(LinearLayout.HORIZONTAL);
                line.setPadding(dp(c, Math.max(0, block.optInt("depth") - 1) * 16), 0, 0, 0);
                TextView marker = text(c, block.optString("marker"), 15, false);
                marker.setTextColor(MUTED);
                line.addView(marker, new LinearLayout.LayoutParams(dp(c, 28), -2));
                line.addView(text(c, block.optString("html"), 16, true),
                        new LinearLayout.LayoutParams(0, -2, 1));
                view = line;
                bottom = 7;
            } else {
                int level = block.optInt("level", 0);
                TextView body = text(c, block.optString("html"),
                        type.equals("heading") ? (level <= 1 ? 23 : level == 2 ? 20 : 17) : 16, true);
                if (type.equals("heading")) {
                    body.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
                    body.setLineSpacing(dp(c, 2), 1.05f);
                    top = i == 0 ? 0 : 10;
                    bottom = 10;
                } else if (type.equals("quote")) {
                    LinearLayout quote = new LinearLayout(c);
                    quote.setBackground(surface(c, Color.rgb(245, 247, 252)));
                    quote.setPadding(0, dp(c, 10), dp(c, 12), dp(c, 10));
                    View stripe = new View(c);
                    stripe.setBackgroundColor(Color.rgb(158, 182, 222));
                    quote.addView(stripe, new LinearLayout.LayoutParams(dp(c, 3), -1));
                    body.setTextColor(MUTED);
                    LinearLayout.LayoutParams bodyParams = new LinearLayout.LayoutParams(0, -2, 1);
                    bodyParams.leftMargin = dp(c, 12);
                    quote.addView(body, bodyParams);
                    view = quote;
                    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
                    params.bottomMargin = dp(c, bottom);
                    content.addView(view, params);
                    continue;
                }
                view = body;
            }
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, type.equals("divider") ? dp(c, 1) : -2);
            params.topMargin = dp(c, top);
            params.bottomMargin = i == blocks.length() - 1 ? 0 : dp(c, bottom);
            content.addView(view, params);
        }
        return content;
    }

    private static View code(Context c, JSONObject block) {
        LinearLayout box = column(c);
        box.setBackground(surface(c, Color.rgb(244, 246, 250)));
        box.setPadding(dp(c, 12), dp(c, 8), dp(c, 12), dp(c, 12));
        LinearLayout header = new LinearLayout(c);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView label = text(c, block.optString("language", "").isEmpty() ? "代码" : block.optString("language"), 11, false);
        label.setTextColor(MUTED);
        label.setTextIsSelectable(false);
        header.addView(label, new LinearLayout.LayoutParams(0, -2, 1));
        Button copy = new Button(c);
        copy.setText("复制");
        copy.setTextSize(12);
        copy.setAllCaps(false);
        copy.setMinHeight(0);
        copy.setMinimumHeight(0);
        copy.setMinWidth(0);
        copy.setMinimumWidth(0);
        copy.setTextColor(MUTED);
        copy.setBackgroundColor(Color.TRANSPARENT);
        copy.setOnClickListener(v -> {
            ClipboardManager clipboard = (ClipboardManager) c.getSystemService(Context.CLIPBOARD_SERVICE);
            if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("代码", block.optString("text")));
        });
        header.addView(copy, new LinearLayout.LayoutParams(dp(c, 56), dp(c, 40)));
        box.addView(header);
        HorizontalScrollView scroll = new HorizontalScrollView(c);
        TextView body = text(c, block.optString("text"), 13, false);
        body.setTypeface(Typeface.MONOSPACE);
        body.setHorizontallyScrolling(true);
        body.setLineSpacing(dp(c, 3), 1.0f);
        scroll.addView(body, new HorizontalScrollView.LayoutParams(-2, -2));
        box.addView(scroll);
        return box;
    }

    private static View table(Context c, JSONArray rows) {
        HorizontalScrollView scroll = new HorizontalScrollView(c);
        LinearLayout table = column(c);
        if (rows != null) for (int r = 0; r < rows.length(); r++) {
            JSONArray cells = rows.optJSONArray(r);
            if (cells == null) continue;
            LinearLayout row = new LinearLayout(c);
            row.setBackgroundColor(r == 0 ? Color.rgb(235, 240, 249)
                    : r % 2 == 0 ? Color.rgb(248, 250, 253) : Color.WHITE);
            for (int j = 0; j < cells.length(); j++) {
                JSONObject cell = cells.optJSONObject(j);
                if (cell == null) continue;
                TextView body = text(c, cell.optString("html"), 14, true);
                body.setPadding(dp(c, 12), dp(c, 10), dp(c, 12), dp(c, 10));
                if (cell.optBoolean("header")) body.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                row.addView(body, new LinearLayout.LayoutParams(dp(c, 148), -2));
            }
            table.addView(row);
            View rule = new View(c);
            rule.setBackgroundColor(Color.rgb(224, 229, 241));
            table.addView(rule, new LinearLayout.LayoutParams(-1, dp(c, 1)));
        }
        scroll.addView(table);
        return scroll;
    }
}
