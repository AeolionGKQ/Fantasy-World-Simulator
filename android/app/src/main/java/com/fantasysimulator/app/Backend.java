package com.fantasysimulator.app;

import android.content.Context;
import android.util.Log;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

/**
 * The game's Python backend (android_bridge.py) inside this process. Python starts once on a
 * background thread; every API call then runs off the UI thread on a small bounded pool.
 */
public final class Backend {

    private static final String TAG = "FantasyBackend";
    private static final CountDownLatch started = new CountDownLatch(1);
    private static final ExecutorService pool = new ThreadPoolExecutor(
        4, 4, 30, TimeUnit.SECONDS, new LinkedBlockingQueue<>(64), runnable -> {
            Thread thread = new Thread(runnable, "fantasy-backend");
            thread.setDaemon(true);
            return thread;
        }
    );
    private static volatile PyObject bridge;
    private static volatile Context appContext;
    private static volatile String startError;
    private static boolean starting;

    private Backend() {}

    /** One API response: status, headers (JSON object text) and raw body. */
    public static final class Response {
        public final int status;
        public final JSONObject headers;
        public final byte[] body;

        Response(int status, JSONObject headers, byte[] body) {
            this.status = status;
            this.headers = headers;
            this.body = body;
        }

        String contentType() {
            String type = headers.optString("Content-Type", "application/octet-stream");
            return type.split(";", 2)[0].trim();
        }

        boolean isText() {
            String type = contentType();
            return type.startsWith("text/") || type.equals("application/json");
        }
    }

    public static synchronized void start(Context context) {
        if (starting) return;
        starting = true;
        Context app = context.getApplicationContext();
        appContext = app;
        Thread thread = new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(app));
                PyObject module = Python.getInstance().getModule("android_bridge");
                module.callAttr("start", new File(app.getFilesDir(), "game-data").getAbsolutePath());
                bridge = module;
                JobKeepAliveService.startIfBusy(app);  // jobs resumed from the last session
            } catch (Throwable error) {
                startError = String.valueOf(error);
                Log.e(TAG, "Python backend failed to start", error);
            } finally {
                started.countDown();
            }
        }, "fantasy-backend-start");
        thread.setDaemon(true);
        thread.start();
    }

    /** Run work on the backend pool; false when the pool is full. */
    public static boolean submit(Runnable work) {
        try {
            pool.execute(work);
            return true;
        } catch (RejectedExecutionException error) {
            return false;
        }
    }

    /** Blocking; never call on the UI thread. */
    public static Response call(String method, String path, JSONObject headers, byte[] body) {
        try {
            started.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return error(503, "SERVICE_STARTING", "游戏服务正在启动，请稍后重试");
        }
        if (bridge == null) {
            return error(500, "BACKEND_START_FAILED", "游戏服务启动失败：" + startError);
        }
        try {
            List<PyObject> result = bridge.callAttr("request", method, path, headers.toString(), body).asList();
            Response response = new Response(
                result.get(0).toInt(),
                new JSONObject(result.get(1).toString()),
                result.get(2).toJava(byte[].class)
            );
            // A write may have started a job; keep the app awake until it ends.
            if (!"GET".equals(method)) JobKeepAliveService.startIfBusy(appContext);
            return response;
        } catch (Throwable error) {
            Log.e(TAG, "API call failed: " + method + " " + path.split("\\?", 2)[0], error);
            return error(500, "INTERNAL_ERROR", "服务器发生内部错误");
        }
    }

    /** Whether a character, story or image job is running. */
    public static boolean isBusy() {
        PyObject module = bridge;
        if (module == null) return false;
        try {
            return module.callAttr("busy").toBoolean();
        } catch (Throwable error) {
            Log.e(TAG, "Job check failed", error);
            return false;
        }
    }

    static Response busy() {
        return error(503, "SERVICE_BUSY", "请求过多，请稍后重试");
    }

    private static Response error(int status, String code, String message) {
        try {
            JSONObject problem = new JSONObject()
                .put("code", code).put("message", message)
                .put("fields", new JSONObject()).put("retryable", status == 503);
            byte[] body = new JSONObject().put("error", problem).toString().getBytes(StandardCharsets.UTF_8);
            return new Response(status, new JSONObject().put("Content-Type", "application/json; charset=utf-8"), body);
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
