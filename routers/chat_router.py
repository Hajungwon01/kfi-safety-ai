from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import chat_service
from deps import soft_auth

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatBody(BaseModel):
    message: str
    context: dict | None = None


@router.post("")
def chat(body: ChatBody, user=Depends(soft_auth)):
    # 로그인 상태면(soft_auth) 채팅으로 합격표시번호를 조회할 때 2부처럼 내 소화기함에
    # 자동 등록까지 해준다. 비로그인이어도 조회 자체는 그대로 동작(등록만 생략).
    result = chat_service.answer_chat(body.message, body.context, user)
    if result.get("error"):
        if result["error"] == "message가 필요합니다.":
            raise HTTPException(status_code=400, detail=result["error"])
        # LLM 호출 실패: Node판과 동일하게 sources를 유지한 채 502 반환
        return JSONResponse(status_code=502, content=result)
    return result
