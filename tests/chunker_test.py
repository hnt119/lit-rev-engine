parsed = parse_pdf(paths[0])

chunks = chunk_text(parsed["text"])

print(f"Created {len(chunks)} chunks")

print(chunks[0]["text"][:500])