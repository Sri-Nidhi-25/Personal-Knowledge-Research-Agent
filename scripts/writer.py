import sys, base64, os

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python writer.py <filepath> <base64_content>')
        sys.exit(1)
    filepath = sys.argv[1]
    b64_content = sys.argv[2]
    decoded = base64.b64decode(b64_content).decode('utf-8')
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(decoded)
    print(f'Successfully wrote {filepath} ({len(decoded)} chars)')
