from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, deal_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(deal_id, []).append(ws)

    def disconnect(self, deal_id: int, ws: WebSocket) -> None:
        try:
            self.active.get(deal_id, []).remove(ws)
        except ValueError:
            pass

    async def broadcast(self, deal_id: int, data: dict) -> None:
        for ws in self.active.get(deal_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


ws_manager = ConnectionManager()
