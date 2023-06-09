import asyncio
from functools import lru_cache
from typing import Annotated, Any, AsyncGenerator
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse
from server.callback import AsyncChunkIteratorCallbackHandler, InfoChunk, TextChunk
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
from server.callback import AsyncChunkIteratorCallbackHandler

from main import load
from server.contracts import call_contract_stake

app = FastAPI()

from login import User, get_current_user, router as loginRouter

app.include_router(loginRouter)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def generate_response(question: str,user:User) -> AsyncGenerator[Any, None]:
    run: asyncio.Task | None = None
    try:
        callback_handler = AsyncChunkIteratorCallbackHandler()

        run = asyncio.create_task(get_agent().run(question, callback_handler))
        print("Running")
        async for response in callback_handler.aiter():
            # check token type
            print("Token:", response)
            if isinstance(response, TextChunk):
                yield response.token + "\n\n"
            elif isinstance(response, InfoChunk):
                print("Info:", response)
                print("InfoDict:", response.__dict__)


            # yield {"done": "", "value": token}

        await run
    except Exception as e:
        print("Caught Exception:", e)
    except BaseException as e:  # asyncio.CancelledError
        print("Caught BaseException:", e)
    finally:
        if run:
            run.cancel()


async def streamer(gen):
    try:
        async for i in gen:
            yield i
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        print("caught cancelled error")


class Ask(BaseModel):
    question: str


@app.post("/ask/")
async def ask(request: Request, body: Ask, current_user: Annotated[User, Depends(get_current_user)]):
    print("Received question:", body.question)
    # get auth header with Bearer split
    # access_token = request.headers.get("Authorization").split(" ")[1]
    # print("access_token:", access_token)
    print(f'current_user:{current_user.address}')

    return StreamingResponse(streamer(generate_response(body.question, current_user)))


@app.on_event("startup")
async def startup():
    print("Server Startup!")
    try:
        await call_contract_stake()
    except Exception as e:
        print("Error calling contract:", e)
        print("Probably RPC node it's down")
    
    get_agent()


@lru_cache()
def get_agent():
    return load()


@app.on_event("shutdown")
async def shutdown():
    print("Server Shutdown!")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=3333, reload=True)
