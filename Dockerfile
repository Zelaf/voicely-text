FROM python:3.12

RUN mkdir /voicely-text

WORKDIR /voicely-text

COPY ["voicely-text.py", "README.md", "./legal", "requirements.txt", "LICENSE", "./"]

RUN pip install -r requirements.txt

CMD ["python", "voicely-text.py"]