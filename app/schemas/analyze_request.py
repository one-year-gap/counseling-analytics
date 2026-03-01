# 키워드 분석 요청 DTO
from pydatic import Field
from app.schemas.base import SchemaBase

class AnalyzeRequest(SchemaBase):
    # 요청 ID
    request_id: str = Field(...,alias="requestId",min_length=1,max_length=200)
    # Batch Jon Instance Id
    job_instance_id: str = Field(...,alias="jobInstanceId",min_length=1,max_length=200)
    #chunckId
    chuck_id: str = Field(...,alias="chuckId",min_length=1,max_length=200)
    #상담 입력 파일 경로
    efs_path_counsel: str = Field(...,alias="efsPathCounsel",min_length=1,max_length=200)
    #상담 별칭 참조 파일 경로
    efs_path_alias: str = Field(...,alias="efsPathAlias",min_length=1,max_length=200)
    #분석 버젼 관리
    analysis_version: str = Field(...,alias="analysisVersion",min_length=1,max_length=200)