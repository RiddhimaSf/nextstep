
from datetime import datetime
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}


def get_time():
    return {"current_time": datetime.now().isoformat()}

def echo(message: str):
    return {"echo": message}

@app.post("/v1/chat")
def chat(tool: str, message: str = ""):
    if tool == "get_time":
        return {"result": get_time()}
    elif tool == "echo":
        return {"result": echo(message)}
    else:
        return {"error": "unknown tool"}
    



