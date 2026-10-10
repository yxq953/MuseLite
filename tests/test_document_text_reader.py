"""Run the production Java text decoder on a JVM without Android dependencies."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_utf8_decoder_and_unicode_pagination(tmp_path):
    root = Path(__file__).resolve().parents[1]
    java_bin = root / "cache" / "tools" / "java17" / "bin"
    javac = str(java_bin / "javac.exe") if (java_bin / "javac.exe").is_file() else shutil.which("javac")
    if not javac:
        pytest.skip("Java compiler and runtime are required for the native decoder test")
    # Use the compiler's matching runtime, avoiding Windows Java shim mismatches.
    java = str(Path(javac).resolve().with_name("java.exe" if Path(javac).suffix.lower() == ".exe" else "java"))
    if not Path(java).is_file():
        pytest.skip("The Java compiler's matching runtime is unavailable")
    harness = tmp_path / "DocumentReaderTest.java"
    harness.write_text(r'''
import com.muselite.python.DocumentTextReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class DocumentReaderTest {
    static void check(boolean ok) { if (!ok) throw new AssertionError(); }
    static DocumentTextReader.Page read(byte[] bytes, int offset, int size) throws Exception {
        return DocumentTextReader.read(new ByteArrayInputStream(bytes), offset, size);
    }
    static void rejects(byte[] bytes, int offset, int size, String message) throws Exception {
        try { read(bytes, offset, size); }
        catch (IllegalArgumentException error) { check(error.getMessage().contains(message)); return; }
        throw new AssertionError("expected rejection: " + message);
    }
    public static void main(String[] args) throws Exception {
        byte[] bytes = "\uFEFF中😀\r\nA".getBytes(StandardCharsets.UTF_8);
        DocumentTextReader.Page first = read(bytes, 0, 2);
        check(first.content.equals("中😀") && first.truncated && first.nextOffset == 2);
        check(first.totalChars == 5 && first.bytes == bytes.length);
        DocumentTextReader.Page second = read(bytes, first.nextOffset, 10);
        check(second.content.equals("\r\nA") && !second.truncated && second.nextOffset == 5);
        check(read(bytes, 5, 10).content.isEmpty());
        check(!read(new byte[0], 0, 1).truncated);
        check(read("\t\n\r\f".getBytes(StandardCharsets.UTF_8), 0, 10).totalChars == 4);
        rejects(bytes, 6, 1, "offset");
        rejects(bytes, -1, 1, "分页");
        rejects(bytes, 0, 0, "分页");
        rejects(bytes, 0, 50001, "分页");
        rejects(new byte[] {(byte) 0xc3, (byte) 0x28}, 0, 1, "UTF-8");
        rejects(new byte[] {(byte) 0xf0, (byte) 0x9f}, 0, 1, "UTF-8");
        rejects(new byte[] {65, 0, 66}, 0, 3, "二进制");
        byte[] full = new byte[1024 * 1024];
        Arrays.fill(full, (byte) 'a');
        check(read(full, 0, 50000).totalChars == full.length);
        rejects(Arrays.copyOf(full, full.length + 1), 0, 1, "1 MiB");
        final int[] consumed = {0};
        InputStream infinite = new InputStream() {
            public int read() { consumed[0]++; return 65; }
            public int read(byte[] target, int offset, int length) {
                Arrays.fill(target, offset, offset + length, (byte) 65);
                consumed[0] += length;
                return length;
            }
        };
        try { DocumentTextReader.read(infinite, 0, 1); throw new AssertionError(); }
        catch (IllegalArgumentException error) { check(consumed[0] <= 1024 * 1024 + 8192); }
        System.out.println("Native document decoder checks passed");
    }
}
''', encoding="utf-8")
    source = root / "java" / "com" / "muselite" / "python" / "DocumentTextReader.java"
    subprocess.run([javac, "-encoding", "UTF-8", "-d", str(tmp_path), str(source), str(harness)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([java, "-cp", str(tmp_path), "DocumentReaderTest"],
                            check=True, capture_output=True, text=True)
    assert "checks passed" in result.stdout
