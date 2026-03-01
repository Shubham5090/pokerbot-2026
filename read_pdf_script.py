import PyPDF2
with open("d:/IITM/Pokerbots/pokerbot-2026/IITPokerbots_PS.pdf", "rb") as f:
    reader = PyPDF2.PdfReader(f)
    for page in reader.pages:
        print(page.extract_text())
