package org.beeware.android;

import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Bundle;
import android.system.Os;
import android.system.ErrnoException;
import android.util.Log;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;

import androidx.activity.EdgeToEdge;
import androidx.activity.SystemBarStyle;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.chaquo.python.Kwarg;
import com.chaquo.python.PyException;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.util.Iterator;
import java.util.List;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONException;
import com.muselite.python.NativeUi;

import {{ cookiecutter.package_name }}.{{ cookiecutter.module_name }}.R;


public class MainActivity extends AppCompatActivity {

    // To profile app launch, use `adb -s MainActivity`; look for "onCreate() start" and "onResume() completed".
    private String TAG = "MainActivity";
    private static PyObject pythonApp;

    /**
     * This method is called by `app.__main__` over JNI in Python when the BeeWare
     * app launches.
     *
     * @param app
     */
    @SuppressWarnings("unused")
    public static void setPythonApp(IPythonApp app) {
        pythonApp = PyObject.fromJava(app);
    }

    /**
     * We store the MainActivity instance on the *class* so that we can easily
     * access it from Python.
     */
    public static MainActivity singletonThis;

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String scheduledTask = intent.getStringExtra("task_id");
        if (scheduledTask != null && !scheduledTask.isEmpty() && Python.isStarted()) {
            try {
                JSONObject data = new JSONObject().put("id", scheduledTask);
                Python.getInstance().getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", "scheduled_task_fire", data.toString());
            } catch (Exception error) { Log.e(TAG, "Unable to handle scheduled task", error); }
            intent.removeExtra("task_id");
        }
        String scheduledSession = intent.getStringExtra("session_id");
        String scheduledPrompt = intent.getStringExtra("prompt");
        if (scheduledSession != null && !scheduledSession.isEmpty() && Python.isStarted()) {
            try {
                JSONObject open = new JSONObject().put("id", scheduledSession);
                String action = "open";
                if (scheduledPrompt != null && !scheduledPrompt.trim().isEmpty()) {
                    open.put("text", scheduledPrompt);
                    action = "scheduled_send";
                }
                Python.getInstance().getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", action, open.toString());
            } catch (Exception error) { Log.e(TAG, "Unable to handle scheduled session", error); }
        }
    }

    protected void onCreate(Bundle savedInstanceState) {
        Log.d(TAG, "onCreate() start");
        // Change away from the splash screen theme to the app theme.
        setTheme(R.style.AppTheme);
        super.onCreate(savedInstanceState);
        singletonThis = this;

        EdgeToEdge.enable(this, SystemBarStyle.dark(getColor(R.color.colorPrimaryDark)));
        getWindow().setStatusBarColor(Color.rgb(248, 250, 255));
        getWindow().setNavigationBarColor(Color.WHITE);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        );
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            getWindow().getInsetsController().setSystemBarsAppearance(
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS |
                android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS |
                android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            );
        }
        View layout = new FrameLayout(this);
        setContentView(
            layout,
            new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
        );

        // setContentView below has given the FrameLayout a position and size that
        // doesn't overlap anything, so use that as the parent of the app's content.
        findViewById(android.R.id.content).setId(View.NO_ID);
        layout.setId(android.R.id.content);

        String environStr = getIntent().getStringExtra("org.beeware.ENVIRON");
        if (environStr != null) {
            try {
                JSONObject environJson = new JSONObject(environStr);
                for (Iterator<String> it = environJson.keys(); it.hasNext(); ) {
                    String key = it.next();
                    String value = environJson.getString(key);
                    Os.setenv(key, value, true);
                }
            } catch (JSONException e) {
                throw new RuntimeException(e);
            } catch (ErrnoException e) {
                throw new RuntimeException(e);
            }
        }

        Python py;
        if (Python.isStarted()) {
            Log.d(TAG, "Python already started");
            py = Python.getInstance();
        } else {
            Log.d(TAG, "Starting Python");
            AndroidPlatform platform = new AndroidPlatform(this);
            platform.redirectStdioToLogcat();
            Python.start(platform);
            py = Python.getInstance();

            String argvStr = getIntent().getStringExtra("org.beeware.ARGV");
            if (argvStr != null) {
                try {
                    JSONArray argvJson = new JSONArray(argvStr);
                    List<PyObject> sysArgv = py.getModule("sys").get("argv").asList();
                    for (int i = 0; i < argvJson.length(); i++) {
                        sysArgv.add(PyObject.fromJava(argvJson.getString(i)));
                    }
                } catch (JSONException e) {
                    throw new RuntimeException(e);
                }
            }
        }

        Log.d(TAG, "Running main module " + getString(R.string.main_module));
        py.getModule("runpy").callAttr(
            "run_module",
            getString(R.string.main_module),
            new Kwarg("run_name", "__main__"),
            new Kwarg("alter_sys", true)
        );

        String scheduledTask = getIntent().getStringExtra("task_id");
        if (scheduledTask != null && !scheduledTask.isEmpty()) {
            try {
                JSONObject data = new JSONObject().put("id", scheduledTask);
                py.getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", "scheduled_task_fire", data.toString());
            } catch (Exception error) { Log.e(TAG, "Unable to handle scheduled task", error); }
            getIntent().removeExtra("task_id");
        }

        String scheduledSession = getIntent().getStringExtra("session_id");
        String scheduledPrompt = getIntent().getStringExtra("prompt");
        if (scheduledSession != null && !scheduledSession.isEmpty()) {
            try {
                JSONObject open = new JSONObject().put("id", scheduledSession);
                String action = "open";
                if (scheduledPrompt != null && !scheduledPrompt.trim().isEmpty()) {
                    open.put("text", scheduledPrompt);
                    action = "scheduled_send";
                }
                py.getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", action, open.toString());
            } catch (Exception error) { Log.e(TAG, "Unable to handle scheduled session", error); }
        }

        userCode("onCreate");
        Log.d(TAG, "onCreate() complete");
    }

    public void setContentView(View view, ViewGroup.LayoutParams lp) {
        super.setContentView(view, lp);

        // EdgeToEdge.enable calls Window.setStatusBarColor, but that has no effect when
        // targeting API level 35 and higher, so we need to manually draw the status bar
        // background (https://stackoverflow.com/q/78832208).
        View statusBarBackground = new View(this);
        statusBarBackground.setBackgroundColor(Color.rgb(248, 250, 255));
        addContentView(
            statusBarBackground,
            new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0)
        );

        // Based on the "Empty Views Activity" from Android Studio Quail 3.
        ViewCompat.setOnApplyWindowInsetsListener(
            view,
            (v, insets) -> {
                // systemBars includes the status bar, navigation bar (which may be on
                // the left or right on API level 28 and older), and action bar.
                Insets systemBars = insets.getInsets(
                    WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout()
                );
                ((ViewGroup.MarginLayoutParams) v.getLayoutParams()).setMargins(
                    systemBars.left, systemBars.top, systemBars.right, systemBars.bottom
                );

                ViewGroup.MarginLayoutParams statusLp =
                    (ViewGroup.MarginLayoutParams) statusBarBackground.getLayoutParams();
                statusLp.height = systemBars.top;
                statusLp.setMargins(systemBars.left, 0, systemBars.right, 0);
                statusBarBackground.requestLayout();

                return insets;
            }
        );
    }

    protected void onStart() {
        Log.d(TAG, "onStart() start");
        super.onStart();
        userCode("onStart");
        Log.d(TAG, "onStart() complete");
    }

    protected void onResume() {
        Log.d(TAG, "onResume() start");
        super.onResume();
        userCode("onResume");
        Log.d(TAG, "onResume() complete");
    }

    protected void onPause() {
        Log.d(TAG, "onPause() start");
        super.onPause();
        userCode("onPause");
        Log.d(TAG, "onPause() complete");
    }

    protected void onStop() {
        Log.d(TAG, "onStop() start");
        super.onStop();
        userCode("onStop");
        Log.d(TAG, "onStop() complete");
    }
    protected void onDestroy() {
        Log.d(TAG, "onDestroy() start");
        super.onDestroy();
        userCode("onDestroy");
        Log.d(TAG, "onDestroy() complete");
    }
    protected void onRestart() {
        Log.d(TAG, "onRestart() start");
        super.onRestart();
        userCode("onRestart");
        Log.d(TAG, "onRestart() complete");
    }
    public void onTopResumedActivityChanged (boolean isTopResumedActivity){
        Log.d(TAG, "onTopResumedActivityChanged() start");
        super.onTopResumedActivityChanged(isTopResumedActivity);
        userCode("onTopResumedActivityChanged", isTopResumedActivity);
        Log.d(TAG, "onTopResumedActivityChanged() complete");
    }

    protected void onActivityResult(int requestCode, int resultCode, Intent data)
    {
        Log.d(TAG, "onActivityResult() start");
        super.onActivityResult(requestCode, resultCode, data);
        userCode("onActivityResult", requestCode, resultCode, data);
        Log.d(TAG, "onActivityResult() complete");
    }

    public void onConfigurationChanged(Configuration newConfig) {
        Log.d(TAG, "onConfigurationChanged() start");
        super.onConfigurationChanged(newConfig);
        userCode("onConfigurationChanged", newConfig);
        Log.d(TAG, "onConfigurationChanged() complete");
    }

    public boolean onOptionsItemSelected(MenuItem menuitem) {
        Log.d(TAG, "onOptionsItemSelected() start");
        PyObject pyResult = userCode("onOptionsItemSelected", menuitem);
        boolean result = (pyResult == null) ? false : pyResult.toBoolean();
        Log.d(TAG, "onOptionsItemSelected() complete");
        return result;
    }

    public boolean onPrepareOptionsMenu(Menu menu) {
        Log.d(TAG, "onPrepareOptionsMenu() start");
        PyObject pyResult = userCode("onPrepareOptionsMenu", menu);
        boolean result = (pyResult == null) ? false : pyResult.toBoolean();
        Log.d(TAG, "onPrepareOptionsMenu() complete");
        return result;
    }

    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults)
    {
        Log.d(TAG, "onRequestPermissionsResult() start");
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        userCode("onRequestPermissionsResult", requestCode, permissions, grantResults);
        Log.d(TAG, "onRequestPermissionsResult() complete");
    }

    private PyObject userCode(String methodName, Object... args) {
        if (pythonApp == null) {
            // Could be a non-graphical app such as Python-support-testbed.
            return null;
        }
        try {
            if (pythonApp.containsKey(methodName)) {
                return pythonApp.callAttr(methodName, args);
            } else {
                // Handle the case where the method doesn't exist
                return null;
            }
        } catch (PyException e) {
            if (e.getMessage().startsWith("NotImplementedError")) {
                return null;
            }
            throw e;
        }
    }
}
