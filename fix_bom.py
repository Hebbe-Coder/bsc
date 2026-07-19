import codecs

with codecs.open('requirements.txt', 'r', 'utf-8-sig') as f:
    content = f.read()

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(content)

print("BOM removed successfully")
