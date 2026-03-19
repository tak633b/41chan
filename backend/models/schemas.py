"""
Pydantic スキーマ定義
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# --- Simulation ---

class SimulationCreate(BaseModel):
    prompt: str
    scale: str = "auto"  # "auto" | "mini" | "full" | "custom"
    # "auto": プロンプト/シード内容を分析して動的にパラメータを決定（推奨）
    # "mini": 固定値（エージェント5人, 2ラウンド）
    # "full": 固定値（エージェント12人, 5ラウンド）
    # "custom": custom_agents / custom_rounds で手動指定
    custom_agents: Optional[int] = None
    custom_rounds: Optional[int] = None


class SeedDataInfo(BaseModel):
    og_image: str = ""
    source_url: str = ""

class SimulationStatus(BaseModel):
    id: str
    theme: str
    prompt: str = ""
    status: str
    progress: float
    round_current: int
    round_total: int
    agent_count: int
    created_at: str
    board_count: int
    total_posts: int
    elapsed_seconds: Optional[float] = None
    seed_info: Optional[SeedDataInfo] = None


class SimulationSummary(BaseModel):
    id: str
    theme: str
    created_at: str
    status: str
    board_count: int
    total_posts: int
    elapsed_seconds: Optional[float] = None


# --- Board ---

class BoardInfo(BaseModel):
    board_id: str
    simulation_id: str
    name: str
    emoji: str
    description: str
    thread_count: int
    post_count: int


# --- Thread ---

class ThreadInfo(BaseModel):
    thread_id: str
    board_id: str
    simulation_id: str
    title: str
    post_count: int
    last_post_at: Optional[str]
    is_active: bool


class PostInfo(BaseModel):
    post_id: str
    post_num: int
    agent_name: str
    username: str
    content: str
    reply_to: Optional[int]
    timestamp: str
    emotion: str = "neutral"


class ThreadDetail(BaseModel):
    thread_id: str
    title: str
    board_name: str
    board_id: str
    simulation_id: str
    posts: List[PostInfo]


# --- Agent ---

class AgentInfo(BaseModel):
    agent_id: str
    name: str
    username: str
    bio: str
    persona: str
    age: int
    gender: str
    mbti: str
    tone_style: str
    profession: str
    interested_topics: List[str]
    post_count: int


class AgentDetail(AgentInfo):
    stance: Dict[str, Any]
    hidden_agenda: str
    recent_posts: List[PostInfo]


# --- Report ---

class ReportData(BaseModel):
    simulation_id: str
    summary: str
    details: str
    confidence: float
    key_findings: List[str]
    agent_positions: Dict[str, str]
    turning_points: List[str]
    consensus: str
    minority_views: List[str]
    prediction: str = ""


# --- Ask ---

class AskRequest(BaseModel):
    question: str


class AskAnswer(BaseModel):
    agent_name: str
    username: str
    content: str
    reply_to: Optional[int] = None
    timestamp: str


class AskHistory(BaseModel):
    question: str
    answers: List[AskAnswer]
    created_at: str
