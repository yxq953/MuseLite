package com.muselite.python;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** API keys are encrypted with a non-exportable Android Keystore AES key. */
public final class SecretStore {
    private static final String ALIAS = "muselite_python_credentials_v1";
    private static final String PREFS = "encrypted_credentials";

    private SecretStore() {}

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }

    private static SharedPreferences prefs(Activity activity) {
        return activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static void put(Activity activity, String name, String value) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        String encoded = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
            Base64.encodeToString(encrypted, Base64.NO_WRAP);
        if (!prefs(activity).edit().putString(name, encoded).commit())
            throw new IllegalStateException("无法保存加密密钥");
    }

    public static String get(Activity activity, String name) throws Exception {
        String encoded = prefs(activity).getString(name, null);
        if (encoded == null) return "";
        String[] parts = encoded.split(":", 2);
        if (parts.length != 2) throw new IllegalStateException("加密数据格式错误");
        byte[] iv = Base64.decode(parts[0], Base64.NO_WRAP);
        byte[] data = Base64.decode(parts[1], Base64.NO_WRAP);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(data), StandardCharsets.UTF_8);
    }

    public static void clear(Activity activity, String name) {
        prefs(activity).edit().remove(name).apply();
    }
}
