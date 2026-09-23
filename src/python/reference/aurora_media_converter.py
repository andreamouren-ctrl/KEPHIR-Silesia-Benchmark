#!/usr/bin/env python3
"""
AURORA Converter v0.1

Native converter into AURORA Media from raw canonical inputs:
- PCM s16le audio
- YUV420p8 video

This converter does not require FFmpeg. Future import adapters may use external
decoders outside the AURORA core to turn MP4/MKV/etc. into these canonical raw
inputs, but .aum creation itself remains native AURORA code.
"""
from aurora_media_pipeline import main
if __name__=="__main__":
    main()
