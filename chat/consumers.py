import asyncio
import random
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.consumer import AsyncConsumer
import redis.asyncio as redis


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Вытаскиваем Username из параметров запроса.
        # Парсим параметры запроса, получаем dict. Значениями этого dict
        # являются list со str.
        # Примеры: {"username": ["admin"]}, {}
        query_parameters = parse_qs(self.scope["query_string"].decode())
        # get возвращает None если ключа нет.
        maybe_username = query_parameters.get("username")
        self.username = maybe_username[0] if maybe_username is not None else "Anon"

        # Из примера django-channels.
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        self.redis = await redis.from_url("redis://localhost:6379")
        await self.accept()
    
    async def disconnect(self, _code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": self.username + ": " + text_data,
            }
        )

        # Примитивная проверка прав.
        if self.username in ("admin", "root"):
            if text_data == "timer start":
                await self.start_timer(60)
            elif text_data == "timer pause":
                await self.pause_timer()
            elif text_data == "timer resume":
                await self.resume_timer()
            elif text_data == "timer stop":
                await self.stop_timer()

    async def chat_message(self, event):
        await self.send(text_data=event["message"])

    async def start_timer(self, time: int):
        """
        Запустить таймер в текущем чате. Прерывает работу ранее
        запущенного таймера в чате, если таковой присутствовал.
        """

        # Генерируем уникальный ID таймера.
        timer_id = bytes(random.getrandbits(8) for _ in range(8))
        await self.redis.set(f"chat-timer:{self.room_group_name}:id", timer_id)
        await self.resume_timer()
        # Запускаем задачу таймера В ФОНЕ. Данная функция не блокирует.
        asyncio.create_task(self.background_timer(self.room_group_name, timer_id, time))

    async def pause_timer(self):
        """
        Поставить таймер на паузу, если он запущен в данной комнате.
        """

        if await self.redis.get(f"chat-timer:{self.room_group_name}:id") is not None:
            await self.redis.set(f"chat-timer:{self.room_group_name}:status", b"paused")

    async def resume_timer(self):
        """
        Снять таймер с паузы, если он запущен в данной комнате.
        """

        if await self.redis.get(f"chat-timer:{self.room_group_name}:id") is not None:
            await self.redis.set(f"chat-timer:{self.room_group_name}:status", b"running")
    
    async def stop_timer(self):
        """
        Полностью остановить и удалить таймер, если он запущен в данной комнате.
        """

        if await self.redis.get(f"chat-timer:{self.room_group_name}:id") is not None:
            await self.redis.delete(f"chat-timer:{self.room_group_name}:id")
            await self.redis.delete(f"chat-timer:{self.room_group_name}:status")

    async def background_timer(self, room_group_name: str, timer_id: bytes, time: int):
        """
        Задача, отправляющее сообщение в чат room_group_name каждую секунду.
        """

        while time != 0:
            # Проверяем, запущен ли в чате таймер вообще (если нет, то get вернёт None),
            # и если запущен, то запущен ли "наш" таймер.
            if await self.redis.get(f"chat-timer:{room_group_name}:id") != timer_id:
                break

            # Проверяем статус таймера.
            status = await self.redis.get(f"chat-timer:{room_group_name}:status")
            if status == b"running":
                await self.channel_layer.group_send(
                    room_group_name,
                    {
                        "type": "chat_message",
                        "message": f"time left: {time}",
                    }
                )
                time -= 1
            elif status == b"paused":
                pass
            else:
                # Sanity check.
                raise ValueError(f"Unexpected status: {status!r}")

            # В любом случае ждём одну секунду.
            await asyncio.sleep(1)

