package com.muselite.python;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Bounded UTF-8 decoding and Unicode character pagination for phone documents. */
public final class DocumentTextReader {
    private static final int MAX_BYTES = 1024 * 1024;

    private DocumentTextReader() {}

    public static final class Page {
        public final String content;
        public final int bytes, totalChars, nextOffset;
        public final boolean truncated;

        private Page(String content, int bytes, int totalChars, int nextOffset) {
            this.content = content;
            this.bytes = bytes;
            this.totalChars = totalChars;
            this.nextOffset = nextOffset;
            this.truncated = nextOffset < totalChars;
        }
    }

    public static Page read(InputStream input, int offset, int maxChars) throws Exception {
        if (offset < 0 || maxChars < 1 || maxChars > 50000)
            throw new IllegalArgumentException("文本读取分页参数超出范围");
        if (input == null) throw new IllegalStateException("无法打开文档");
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (data.size() + count > MAX_BYTES)
                throw new IllegalArgumentException("文本文件超过 1 MiB，暂不支持直接读取");
            data.write(buffer, 0, count);
        }
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(data.toByteArray())).toString();
        } catch (CharacterCodingException error) {
            throw new IllegalArgumentException("文件不是 UTF-8 文本，请先转换编码；PDF、Word 等二进制文档不能直接读取");
        }
        if (text.startsWith("\uFEFF")) text = text.substring(1);
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch < 32 && ch != '\n' && ch != '\r' && ch != '\t' && ch != '\f')
                throw new IllegalArgumentException("文件包含二进制数据，不能作为文本读取");
        }
        int total = text.codePointCount(0, text.length());
        if (offset > total) throw new IllegalArgumentException("offset 超过文本字符数：" + total);
        int next = offset + Math.min(maxChars, total - offset);
        return new Page(text.substring(text.offsetByCodePoints(0, offset), text.offsetByCodePoints(0, next)),
            data.size(), total, next);
    }
}
