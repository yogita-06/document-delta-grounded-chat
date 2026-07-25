# Limitations

- DWG is a genuine adapter stub; production support needs ODA conversion and ezdxf.
- Visual PDF markup returns HTTP 501 and does not affect the core pipeline.
- OCR requires a separately installed Tesseract executable and is sensitive to drawing density.
- Split/merged blocks and dense tables are approximated at line level.
- Vector geometry is not semantically compared in this take-home implementation.
- In-process synchronous execution and local indexes are intended for a single-node demo.
- The OpenAI prose provider is not wired into core operation; mock grounded synthesis is the safe default.
