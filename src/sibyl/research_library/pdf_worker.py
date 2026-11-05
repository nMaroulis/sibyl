"""Child-process PDF reader. Never execute document JavaScript, open URLs or perform OCR."""

import json
import logging
import sys


def main():
    """Bound CPU, pages, decoded streams and returned text; the parent also enforces wall time."""
    logging.disable(logging.CRITICAL)
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    except (ImportError, OSError, ValueError):
        pass  # Windows still has the parent's hard wall-time limit.
    from pypdf import PdfReader, overwrite_configuration

    # Use pypdf's current native limits, rather than deprecated module constants.
    maximum = 8 * 1024 * 1024
    overwrite_configuration(
        maximum_declared_stream_length=maximum,
        array_based_stream_maximum_output_length=maximum,
        zlib_maximum_output_length=maximum,
        lzw_maximum_output_length=maximum,
        run_length_maximum_output_length=maximum,
        brotli_maximum_output_length=maximum,
        jbig2_maximum_output_length=maximum,
        image_maximum_buffer_size=maximum,
        stream_decoding_work_maximum_length=4 * maximum,
    )
    reader = PdfReader(sys.argv[1], strict=True)
    if reader.is_encrypted or len(reader.pages) > 100:
        raise ValueError("Unsupported PDF size or encryption.")
    pages, total = [], 0
    for number, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > 8 * 1024 * 1024:
            raise ValueError("PDF content stream too large.")
        text = page.extract_text() or ""
        total += len(text)
        if total > 1_000_000:
            raise ValueError("PDF text too large.")
        pages.append({"page": number, "text": text})
    print(json.dumps(pages))


if __name__ == "__main__":
    main()
