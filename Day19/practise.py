from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken 
from pathlib import Path
SCRIPT_DIR = Path(__file__).parent
file_path = SCRIPT_DIR / "текст_для_практики.txt"
encoder = tiktoken.get_encoding('cl100k_base')

with open(file_path, "r",encoding="utf-8") as f:
    text = f.read()

def fixed_size_chunking_manual(text:str, size : int = 500, overlap: int = 100) -> list[str]:
    if overlap >= size:
        raise ValueError("chunk_overlap должен быть строго меньше chunk_size")


    tokens = encoder.encode(text)
    chunks = []

    for i in range(0, len(tokens), size - overlap):
        chunks.append(encoder.decode(tokens[i:i + size]))
    return chunks

def recursive_chunking(text:str, size : int = 500, overlap: int = 100) -> list[str]:
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", 
        chunk_size=size,
        chunk_overlap=overlap
    )

    chunks = text_splitter.split_text(text)

    return chunks


def get_stats(chunks:list[str]):
    lens = [len(encoder.encode(chunk)) for chunk in chunks]
    return {
        "count": len(chunks),
        "min": min(lens),
        "max": max(lens),
        "avg_size": round(sum(lens) / len(lens), 1),
    }

def main():
    fixed_chunks = fixed_size_chunking_manual(text)
    recursive_chunks = recursive_chunking(text)
    fixed_stats = get_stats(fixed_chunks)
    recursive_stats = get_stats(recursive_chunks)

    print("------ Fixed chunks ------")
    print(f"Количество чанков [{fixed_stats['count']}], "
          f"min [{fixed_stats['min']}], "
          f"max [{fixed_stats['max']}], "
          f"avg [{fixed_stats['avg_size']}] токенов")
    for i, chunk in enumerate(fixed_chunks):
        print(f"\n--- fixed[{i}] ---")
        print(chunk)

    print("\n------ Recursive chunks ------")
    print(f"Количество чанков [{recursive_stats['count']}], "
          f"min [{recursive_stats['min']}], "
          f"max [{recursive_stats['max']}], "
          f"avg [{recursive_stats['avg_size']}] токенов")
    for i, chunk in enumerate(recursive_chunks):
        print(f"\n--- recursive[{i}] ---")
        print(chunk)

if __name__ == "__main__":
    main()


