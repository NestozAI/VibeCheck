"""
데이터베이스 모델
"""

from datetime import datetime
from typing import Optional
import secrets

from sqlalchemy import Column, String, DateTime, Boolean, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


def generate_api_key() -> str:
    """API Key 생성 (vibe_sk_xxxx 형식)"""
    return f"vibe_sk_{secrets.token_hex(16)}"


class Workspace(Base):
    """워크스페이스 테이블 (OAuth로 설치된 워크스페이스)"""
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Slack 워크스페이스 정보
    team_id = Column(String, unique=True, index=True)
    team_name = Column(String)

    # OAuth 토큰
    bot_token = Column(String)  # xoxb-xxx
    bot_user_id = Column(String)  # 봇 유저 ID

    # 설치한 사람
    installer_user_id = Column(String)

    # 타임스탬프
    installed_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """유저 테이블"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Slack 정보
    slack_user_id = Column(String, unique=True, index=True)
    slack_team_id = Column(String, index=True)  # 워크스페이스 ID
    slack_channel_id = Column(String)  # DM 채널

    # API Key
    api_key = Column(String, unique=True, index=True, default=generate_api_key)

    # 상태
    agent_connected = Column(Boolean, default=False)

    # 사용량
    usage_count = Column(Integer, default=0)
    usage_limit = Column(Integer, default=100)  # 무료 플랜 기본값

    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """메시지 로그 테이블"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)

    direction = Column(String)  # "user_to_agent" or "agent_to_user"
    content = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)


# 데이터베이스 설정
DATABASE_URL = "sqlite:///./vibecheck.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """데이터베이스 초기화"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """DB 세션 가져오기"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
