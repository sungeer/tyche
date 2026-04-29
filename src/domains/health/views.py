from src.core.response import ok
from src.domains.health import service


async def startup_probe(request):
    if not app_started:
        raise HTTPException(status_code=503, detail="starting")
    return {"status": "started"}


async def liveness(request):
    data = {'status': 'alive'}
    return ok(data)


async def readiness(request):
    await service.check_db_conn()
    data = {'status': 'ready'}
    return ok(data)
