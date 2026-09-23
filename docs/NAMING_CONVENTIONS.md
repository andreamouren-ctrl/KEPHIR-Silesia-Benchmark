# Naming Conventions

## Product names

Use:
- AURORA Media
- AURORA Audio
- AURORA Video
- AURORA Stream
- AURORA Container
- KHEPRI

Do not use experimental KS/KSV names as product names.

## C++ production files

PascalCase:
- AuroraMediaContainer.h
- AuroraMediaContainer.cpp
- AuroraStreamProtocol.h
- AuroraMediaSession.cpp

## Python reference files

Lowercase snake_case, descriptive:
- aurora_media_container.py
- aurora_media_codec_bridge.py
- aurora_media_pipeline.py
- aurora_stream_protocol.py

## Experiments

Keep historical identifiers:
- ks01_...
- ks06_...
- ksv03_...
- ksv05_...

The prefix is valuable for chronological traceability.

## Result files

Uppercase checkpoint identifier plus descriptive suffix:
- KS04_FULL256_RESULTS.md
- KSV05_ADAPTIVE_ROUTING_RESULTS.md

## Documentation

Descriptive uppercase names for canonical engineering documents:
- AURORA_MEDIA_TECHNICAL_MASTER.md
- AURORA_MEDIA_FORMAT_V01.md
- BACKEND_ROADMAP.md

## Versioning

Use explicit versions only for binary/spec compatibility boundaries.

Do not create a new product version for every research experiment.
