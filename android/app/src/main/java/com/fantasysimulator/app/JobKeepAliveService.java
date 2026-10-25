package com.fantasysimulator.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import androidx.core.app.NotificationCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.ContextCompat;

/**
 * Keeps the app running while a character, story or image job is in progress. Without it Android
 * freezes the process soon after the player switches away, and the model request in flight is cut
 * off. The service stops itself as soon as the backend has no job left.
 */
public class JobKeepAliveService extends Service {

    private static final String TAG = "FantasyBackend";
    private static final String CHANNEL = "story-jobs";
    private static final int NOTIFICATION_ID = 1;
    private static final long CHECK_EVERY_MS = 2000;
    private static final long WAKE_LOCK_LIMIT_MS = 30 * 60 * 1000;

    private static volatile boolean running;
    private Thread watcher;
    private PowerManager.WakeLock wakeLock;

    /** Start the service if a job is running and it is not up yet; call off the UI thread. */
    public static void startIfBusy(Context context) {
        if (running || !Backend.isBusy()) return;
        try {
            ContextCompat.startForegroundService(context, new Intent(context, JobKeepAliveService.class));
        } catch (RuntimeException error) {
            // Android refuses a foreground service started from the background; the job still
            // runs as long as the app stays open.
            Log.w(TAG, "Could not keep the app awake for a running job", error);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        createChannel();
        Intent open = new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_story)
            .setContentTitle(getString(R.string.job_notification_title))
            .setContentText(getString(R.string.job_notification_text))
            .setContentIntent(content)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ? ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC : 0;
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type);
        running = true;
        if (wakeLock == null) {
            PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
            wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "FantasySimulator:story-job");
            wakeLock.acquire(WAKE_LOCK_LIMIT_MS);
        }
        if (watcher == null) {
            watcher = new Thread(this::stopWhenIdle, "fantasy-job-watcher");
            watcher.setDaemon(true);
            watcher.start();
        }
        return START_NOT_STICKY;
    }

    private void stopWhenIdle() {
        try {
            do {
                Thread.sleep(CHECK_EVERY_MS);
            } while (Backend.isBusy());
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
        stopSelf();
    }

    @Override
    public void onTimeout(int startId, int fgsType) {
        // Android 15 limits how long a data-sync service may run; give the time back.
        stopSelf();
    }

    @Override
    public void onDestroy() {
        running = false;
        if (watcher != null) watcher.interrupt();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL, getString(R.string.job_channel_name), NotificationManager.IMPORTANCE_LOW
        );
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }
}
