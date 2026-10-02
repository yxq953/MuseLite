package com.muselite.python;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** Keeps a user-started phone task alive while another app is foregrounded. */
public final class PhoneTaskService extends Service {
    static final String ACTION_START = "com.muselite.python.PHONE_START";
    static final String ACTION_STOP = "com.muselite.python.PHONE_STOP";
    private static final String CHANNEL = "phone_task";
    private static volatile boolean stopRequested = true;
    private static volatile boolean running = false;

    static void clearStop() { stopRequested = false; }
    static void requestStop() { stopRequested = true; }
    static boolean stopRequested() { return stopRequested; }
    static boolean running() { return running; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || ACTION_STOP.equals(intent.getAction())) {
            requestStop(); running = false; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf();
            return START_NOT_STICKY;
        }
        if (!ACTION_START.equals(intent.getAction())) return START_NOT_STICKY;
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "手机操作任务",
            NotificationManager.IMPORTANCE_LOW));
        Intent stop = new Intent(this, PhoneTaskService.class).setAction(ACTION_STOP);
        PendingIntent stopIntent = PendingIntent.getService(this, 51, stop,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentTitle("MuseLite 正在操作手机")
            .setContentText("点击停止可中断当前 Agent 任务")
            .setOngoing(true)
            .addAction(new Notification.Action.Builder(null, "停止", stopIntent).build())
            .build();
        if (Build.VERSION.SDK_INT >= 34)
            startForeground(7152, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(7152, notification);
        running = true;
        return START_NOT_STICKY;
    }

    @Override public void onDestroy() { running = false; requestStop(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent) { return null; }
}
