package com.fantasysimulator.app;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Seals API keys with an AES key that never leaves the Android Keystore. Called from Python
 * (android_bridge._KeystoreSecretStore); the sealed text is what the key files hold.
 */
public final class SecretCipher {

    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String ALIAS = "fantasy-simulator-api-keys";
    private static final String PREFIX = "ks1:";

    private SecretCipher() {}

    public static synchronized String seal(String plain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] sealed = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
        return PREFIX + encode(cipher.getIV()) + ":" + encode(sealed);
    }

    public static synchronized String open(String stored) throws Exception {
        if (!stored.startsWith(PREFIX)) throw new IllegalArgumentException("unknown key file format");
        String[] parts = stored.substring(PREFIX.length()).split(":", 2);
        if (parts.length != 2) throw new IllegalArgumentException("unknown key file format");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, decode(parts[0])));
        return new String(cipher.doFinal(decode(parts[1])), StandardCharsets.UTF_8);
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(
            new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        );
        return generator.generateKey();
    }

    private static String encode(byte[] bytes) {
        return Base64.encodeToString(bytes, Base64.NO_WRAP);
    }

    private static byte[] decode(String text) {
        return Base64.decode(text, Base64.NO_WRAP);
    }
}
