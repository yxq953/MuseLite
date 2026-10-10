package com.muselite.python;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.UriPermission;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.webkit.MimeTypeMap;
import org.json.JSONObject;
import org.json.JSONArray;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Persistent Storage Access Framework access to a user-selected document folder. */
public final class DocumentBridge {
    private static final int PICK_FOLDER = 7314;
    private static final int GRANTS = Intent.FLAG_GRANT_READ_URI_PERMISSION |
                                      Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    private static final long MAX_BYTES = 25L * 1024 * 1024;

    private DocumentBridge() {}

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("document_folder", Context.MODE_PRIVATE);
    }

    public static void chooseFolder(Activity activity) {
        activity.runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                intent.addFlags(GRANTS | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION |
                                Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
                String previous = preferences(activity).getString("uri", "");
                if (!previous.isEmpty())
                    intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, Uri.parse(previous));
                activity.startActivityForResult(intent, PICK_FOLDER);
            } catch (Exception error) { NativeUi.status("无法打开文件夹选择器：" + error.getMessage(), true); }
        });
    }

    public static boolean onActivityResult(Activity activity, int request, int result, Intent data) {
        if (request != PICK_FOLDER) return false;
        if (result != Activity.RESULT_OK || data == null || data.getData() == null) return true;
        try {
            Uri uri = data.getData();
            int flags = data.getFlags() & GRANTS;
            if ((flags & GRANTS) != GRANTS)
                throw new IllegalStateException("请授予所选文件夹的读写权限");
            ContentResolver resolver = activity.getContentResolver();
            Uri root = root(uri);
            JSONObject info = metadata(resolver, root);
            if (!info.getString("mime").equals(DocumentsContract.Document.MIME_TYPE_DIR))
                throw new IllegalStateException("请选择文件夹");
            if ((info.getInt("flags") & DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE) == 0)
                throw new IllegalStateException("所选文件夹不可写，请选择其他目录");
            resolver.takePersistableUriPermission(uri, flags);
            String previous = preferences(activity).getString("uri", "");
            preferences(activity).edit().putString("uri", uri.toString()).apply();
            if (!previous.isEmpty() && !previous.equals(uri.toString())) release(activity, Uri.parse(previous));
            NativeUi.documentState(status(activity).toString());
            NativeUi.status("文档保存目录已连接", false);
        } catch (Exception error) {
            NativeUi.status("文件夹授权失败：" + error.getMessage(), true);
        }
        return true;
    }

    private static void release(Activity activity, Uri uri) {
        try { activity.getContentResolver().releasePersistableUriPermission(uri, GRANTS); }
        catch (Exception ignored) {}
    }

    public static synchronized void clearFolder(Activity activity) {
        String previous = preferences(activity).getString("uri", "");
        preferences(activity).edit().remove("uri").apply();
        if (!previous.isEmpty()) release(activity, Uri.parse(previous));
        NativeUi.documentState(status(activity).toString());
        NativeUi.status("已断开文档保存目录，已保存的文件仍保留", false);
    }

    private static Uri root(Uri tree) {
        return DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
    }

    private static JSONObject metadata(ContentResolver resolver, Uri uri) throws Exception {
        String[] projection = { DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE, DocumentsContract.Document.COLUMN_FLAGS };
        try (Cursor cursor = resolver.query(uri, projection, null, null, null)) {
            if (cursor == null || !cursor.moveToFirst())
                throw new IllegalStateException("文件夹或文件已不存在，请重新选择保存目录");
            return new JSONObject().put("name", cursor.getString(0))
                .put("mime", cursor.getString(1)).put("flags", cursor.getInt(2));
        }
    }

    private static String displayPath(Uri tree, String name) {
        // A content URI is authoritative. Only the primary local provider maps to this path.
        if ("com.android.externalstorage.documents".equals(tree.getAuthority())) {
            String id = DocumentsContract.getTreeDocumentId(tree);
            if (id.startsWith("primary:")) return "/storage/emulated/0/" + id.substring(8);
        }
        return name;
    }

    public static JSONObject status(Activity activity) {
        JSONObject result = new JSONObject();
        try {
            String saved = preferences(activity).getString("uri", "");
            result.put("configured", false).put("uri", saved);
            if (saved.isEmpty()) return result.put("message", "尚未选择，请点击“选择手机文件夹”");
            Uri tree = Uri.parse(saved);
            boolean granted = false;
            for (UriPermission permission : activity.getContentResolver().getPersistedUriPermissions()) {
                if (permission.getUri().equals(tree) && permission.isReadPermission() && permission.isWritePermission())
                    granted = true;
            }
            if (!granted) return result.put("message", "目录授权已失效，请重新选择文件夹");
            JSONObject info = metadata(activity.getContentResolver(), root(tree));
            if (!info.getString("mime").equals(DocumentsContract.Document.MIME_TYPE_DIR) ||
                (info.getInt("flags") & DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE) == 0)
                return result.put("message", "所选目录不可写，请重新选择文件夹");
            return result.put("configured", true).put("name", info.getString("name"))
                .put("path", displayPath(tree, info.getString("name"))).put("message", "目录已连接");
        } catch (Exception error) {
            try { result.put("configured", false).put("message", "目录不可用，请重新选择：" + error.getMessage()); }
            catch (Exception ignored) {}
            return result;
        }
    }

    private static Uri child(ContentResolver resolver, Uri tree, Uri parent, String name) throws Exception {
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getDocumentId(parent));
        try (Cursor cursor = resolver.query(children, new String[] {
                DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME },
                null, null, null)) {
            if (cursor == null) throw new IllegalStateException("无法读取文件夹");
            while (cursor.moveToNext()) {
                if (name.equals(cursor.getString(1)))
                    return DocumentsContract.buildDocumentUriUsingTree(tree, cursor.getString(0));
            }
        }
        return null;
    }

    private static String mime(String name) {
        int dot = name.lastIndexOf('.');
        String extension = dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
        if (extension.equals("md") || extension.equals("markdown")) return "text/markdown";
        String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
        return mime == null ? "application/octet-stream" : mime;
    }

    private static String[] pathParts(String path, boolean allowRoot) {
        if (allowRoot && path.isEmpty()) return new String[0];
        String[] parts = path.split("/", -1);
        for (String part : parts) {
            if (part.trim().isEmpty() || part.equals(".") || part.equals(".."))
                throw new IllegalArgumentException("文档路径必须是目录内的相对路径");
            for (int i = 0; i < part.length(); i++) {
                char ch = part.charAt(i);
                if (ch < 32 || "\\:*?\"<>|".indexOf(ch) >= 0)
                    throw new IllegalArgumentException("文档路径包含不支持的字符");
            }
        }
        return parts;
    }

    private static JSONObject selectedDirectory(Activity activity) throws Exception {
        JSONObject directory = status(activity);
        if (!directory.getBoolean("configured"))
            throw new IllegalStateException(directory.optString("message") + "；请在设置 > 文档保存目录中选择文件夹");
        return directory;
    }

    private static Uri resolve(ContentResolver resolver, Uri tree, String path, boolean allowRoot) throws Exception {
        Uri current = root(tree);
        for (String part : pathParts(path, allowRoot)) {
            if (!metadata(resolver, current).getString("mime").equals(DocumentsContract.Document.MIME_TYPE_DIR))
                throw new IllegalArgumentException("路径中的父目录不是文件夹");
            current = child(resolver, tree, current, part);
            if (current == null) throw new IllegalArgumentException("文件或文件夹不存在：" + path);
        }
        return current;
    }

    private static JSONObject list(Activity activity, JSONObject params) throws Exception {
        JSONObject directory = selectedDirectory(activity);
        ContentResolver resolver = activity.getContentResolver();
        Uri tree = Uri.parse(directory.getString("uri"));
        String path = params.optString("path", "");
        int offset = params.optInt("offset", 0), limit = params.optInt("limit", 100);
        if (offset < 0 || limit < 1 || limit > 200)
            throw new IllegalArgumentException("文件列表分页参数超出范围");
        Uri folder = resolve(resolver, tree, path, true);
        if (!metadata(resolver, folder).getString("mime").equals(DocumentsContract.Document.MIME_TYPE_DIR))
            throw new IllegalArgumentException("请提供文件夹路径");
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getDocumentId(folder));
        JSONArray entries = new JSONArray();
        int total = 0;
        String[] projection = { DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE, DocumentsContract.Document.COLUMN_LAST_MODIFIED };
        try (Cursor cursor = resolver.query(children, projection, null, null, null)) {
            if (cursor == null) throw new IllegalStateException("无法读取目录内容");
            while (cursor.moveToNext()) {
                if (total++ < offset || entries.length() >= limit) continue;
                String name = cursor.getString(1);
                String type = cursor.getString(2);
                entries.put(new JSONObject().put("name", name)
                    .put("path", path.isEmpty() ? name : path + "/" + name)
                    .put("directory", DocumentsContract.Document.MIME_TYPE_DIR.equals(type))
                    .put("mime", type)
                    .put("bytes", cursor.isNull(3) ? JSONObject.NULL : cursor.getLong(3))
                    .put("modified_ms", cursor.isNull(4) ? JSONObject.NULL : cursor.getLong(4)));
            }
        }
        int next = offset + entries.length();
        boolean more = next < total;
        return new JSONObject().put("path", path).put("entries", entries).put("total", total)
            .put("offset", offset).put("has_more", more)
            .put("next_offset", more ? next : JSONObject.NULL);
    }

    private static JSONObject read(Activity activity, JSONObject params) throws Exception {
        JSONObject directory = selectedDirectory(activity);
        ContentResolver resolver = activity.getContentResolver();
        Uri tree = Uri.parse(directory.getString("uri"));
        String path = params.getString("path");
        int offset = params.optInt("offset", 0), maxChars = params.optInt("max_chars", 12000);
        if (offset < 0 || maxChars < 1 || maxChars > 50000)
            throw new IllegalArgumentException("文本读取分页参数超出范围");
        Uri file = resolve(resolver, tree, path, false);
        JSONObject info = metadata(resolver, file);
        String type = info.getString("mime");
        if (type.equals(DocumentsContract.Document.MIME_TYPE_DIR))
            throw new IllegalArgumentException("这是文件夹，请使用 document_list 列出文件");
        if (!(type.startsWith("text/") || type.equals("application/octet-stream") ||
              type.equals("application/json") || type.equals("application/xml") ||
              type.equals("application/javascript") || type.equals("application/yaml") ||
              type.equals("application/x-yaml")))
            throw new IllegalArgumentException("该文件格式不支持直接读取文本（" + type + "）；目前支持 UTF-8 Markdown、TXT、JSON 等文本文件");
        DocumentTextReader.Page page;
        try (InputStream input = resolver.openInputStream(file)) {
            page = DocumentTextReader.read(input, offset, maxChars);
        }
        return new JSONObject().put("path", directory.getString("path") + "/" + path)
            .put("relative_path", path).put("uri", file.toString()).put("mime", type)
            .put("encoding", "utf-8").put("content", page.content).put("bytes", page.bytes)
            .put("total_chars", page.totalChars).put("offset", offset).put("truncated", page.truncated)
            .put("next_offset", page.truncated ? page.nextOffset : JSONObject.NULL);
    }

    private static synchronized JSONObject save(Activity activity, JSONObject params) throws Exception {
        JSONObject directory = selectedDirectory(activity);
        String path = params.getString("path");
        String[] parts = pathParts(path, false);
        if (params.has("content") == params.has("source_file"))
            throw new IllegalArgumentException("必须提供文本或源文件其中一个");
        byte[] text = null;
        File source = null;
        if (params.has("content")) {
            text = params.getString("content").getBytes(StandardCharsets.UTF_8);
            if (text.length > MAX_BYTES) throw new IllegalArgumentException("文档超过 25 MB");
        } else {
            source = new File(params.getString("source_file")).getCanonicalFile();
            if (!source.getPath().startsWith(activity.getFilesDir().getCanonicalPath() + File.separator) || !source.isFile())
                throw new IllegalArgumentException("源文件必须位于应用工作区");
            if (source.length() > MAX_BYTES) throw new IllegalArgumentException("文档超过 25 MB");
        }
        ContentResolver resolver = activity.getContentResolver();
        Uri tree = Uri.parse(directory.getString("uri"));
        Uri parent = root(tree);
        for (int i = 0; i < parts.length - 1; i++) {
            Uri folder = child(resolver, tree, parent, parts[i]);
            if (folder == null) folder = DocumentsContract.createDocument(resolver, parent,
                DocumentsContract.Document.MIME_TYPE_DIR, parts[i]);
            if (folder == null || !metadata(resolver, folder).getString("mime").equals(DocumentsContract.Document.MIME_TYPE_DIR))
                throw new IllegalStateException("无法创建子目录：" + parts[i]);
            // Use the provider's actual folder name in the returned destination.
            parts[i] = metadata(resolver, folder).getString("name");
            parent = folder;
        }
        String original = parts[parts.length - 1];
        String name = original;
        int dot = original.lastIndexOf('.');
        String stem = dot > 0 ? original.substring(0, dot) : original;
        String extension = dot > 0 ? original.substring(dot) : "";
        for (int i = 1; child(resolver, tree, parent, name) != null; i++) {
            if (i > 1000) throw new IllegalStateException("同名文件过多，请使用其他文件名");
            name = stem + " (" + i + ")" + extension;
        }
        Uri destination = DocumentsContract.createDocument(resolver, parent, mime(original), name);
        if (destination == null) throw new IllegalStateException("无法创建文档");
        long bytes = 0;
        try {
            try (InputStream input = text != null ? new ByteArrayInputStream(text) : new FileInputStream(source);
                 OutputStream output = resolver.openOutputStream(destination, "wt")) {
                if (output == null) throw new IllegalStateException("无法写入文档");
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    bytes += count;
                    if (bytes > MAX_BYTES) throw new IllegalArgumentException("文档超过 25 MB");
                    output.write(buffer, 0, count);
                }
                output.flush();
            }
            parts[parts.length - 1] = metadata(resolver, destination).getString("name");
            String actual = String.join("/", parts);
            return new JSONObject().put("saved", true).put("uri", destination.toString())
                .put("relative_path", actual).put("path", directory.getString("path") + "/" + actual)
                .put("bytes", bytes).put("renamed", !actual.equals(path));
        } catch (Exception error) {
            try { DocumentsContract.deleteDocument(resolver, destination); } catch (Exception ignored) {}
            throw error;
        }
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject request = new JSONObject(requestJson);
            String action = request.getString("action");
            JSONObject result;
            if (action.equals("status")) result = status(activity);
            else if (action.equals("list")) result = list(activity, request.getJSONObject("params"));
            else if (action.equals("read")) result = read(activity, request.getJSONObject("params"));
            else if (action.equals("save")) result = save(activity, request.getJSONObject("params"));
            else throw new IllegalArgumentException("未知文档操作：" + action);
            return new JSONObject().put("result", result).toString();
        } catch (Exception error) {
            try { return new JSONObject().put("error", error.getMessage() == null ? error.toString() : error.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"文档操作失败\"}"; }
        }
    }

    public static void testFolder(Activity activity) {
        new Thread(() -> {
            try {
                JSONObject params = new JSONObject().put("path", "MuseLite-保存测试.md")
                    .put("content", "# MuseLite 文档保存测试\n\n手机文件夹连接成功。Agent 可以按你的要求将 Markdown 等文档保存到这里。\n");
                JSONObject result = save(activity, params);
                NativeUi.status("测试文档已保存：" + result.getString("path"), false);
            } catch (Exception error) { NativeUi.status("测试保存失败：" + error.getMessage(), true); }
        }, "document-folder-test").start();
    }
}
