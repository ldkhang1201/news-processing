# Pipeline Architecture

End-to-end data flow: từ feed RSS của các báo điện tử, qua collector +
resolver, đến API public phục vụ client.

```mermaid
flowchart LR
  subgraph Publishers["📰 Vietnamese news publishers"]
    direction TB
    P1[VnExpress]
    P2[Tuổi Trẻ]
    P3[Thanh Niên]
    P4[Dân trí]
    P5[VietnamNet]
    P6[Znews]
  end

  subgraph hehe["🖥️ hehe — CPU host"]
    direction TB
    Cron(("cron<br/>every 15 min"))
    Collector["Collector<br/><i>one-shot job</i>"]
    Dedup[("Dedup store")]

    subgraph kafka["Kafka"]
      Articles[/"articles topic"/]
      Events[/"events topic"/]
    end

    Resolver["Resolver<br/><i>continuous consumer</i>"]
    Backend["Backend API<br/>:8000"]
    Tunnel["Tunnel"]
  end

  subgraph a100["🚀 a100 — GPU host"]
    LLM["LLM<br/><i>qwen2.5:7b</i>"]
  end

  Geocoder["Geocoder"]
  KV[("External KV store<br/><i>predictions + camera events</i>")]
  Edge(("CDN<br/>edge"))
  Client["Browser / API client"]

  Cron --> Collector
  Publishers -- "RSS feed" --> Collector
  Publishers -- "article HTML" --> Collector
  Collector <-- "id seen?" --> Dedup
  Collector -- "publish Article<br/>(JSON, lz4)" --> Articles

  Articles -- "consume" --> Resolver
  Resolver -- "extract traffic events" --> LLM
  Resolver -- "geocode address<br/>(rate-limit 1.1s/req)" --> Geocoder
  Resolver -- "publish TrafficEvent" --> Events

  Events -- "consume" --> Backend
  KV -- "predictions + camera events" --> Backend

  Backend --> Tunnel
  Tunnel <-. "QUIC" .-> Edge
  Edge -- "https://api-jxvm46idy.brevlab.com" --> Client

  classDef external fill:#fff5e6,stroke:#d97706
  classDef store fill:#e0f2fe,stroke:#0284c7
  classDef topic fill:#fef3c7,stroke:#b45309
  class Publishers,Geocoder,Edge,Client,a100 external
  class Dedup,KV store
  class Articles,Events topic
```

## Component summary

| Component | Where | Vai trò |
|---|---|---|
| Publishers | Internet | 6 báo điện tử Việt Nam, mỗi báo có 2-3 RSS feed |
| Collector | hehe | Cron-driven; poll RSS, GET article body, publish lên Kafka |
| Dedup store | hehe | Tập `id` đã publish, tránh re-publish bài cũ |
| Kafka | hehe | Broker local, 2 topic: `articles` và `events` |
| Resolver | hehe | Continuous consumer; LLM extract + geocode; publish event |
| LLM | a100 | qwen2.5:7b chạy GPU; HTTP API |
| Geocoder | external | Address → (lat, long) |
| Backend API | hehe | HTTP API; consume events vào memory + đọc KV store |
| External KV store | bên ngoài | Lưu predictions + camera events (telemetry) |
| Tunnel | hehe | Mở public URL qua tunnel |

## Endpoints

| Path | Source | Mục đích |
|---|---|---|
| `GET /cameras` | local JSON file | 220 camera HCMC |
| `GET /predictions/latest` | KV store | Latest prediction cho mọi camera |
| `GET /predictions/{id}/...` | KV store | Per-camera predictions |
| `GET /events/...` | KV store | Camera telemetry events (chưa có data) |
| `GET /news?limit=N` | Kafka `events` topic | Resolved news events từ resolver |

## Cách view diagram

- **VS Code**: cài extension "Markdown Preview Mermaid Support", mở file → Cmd-Shift-V
- **GitHub**: render trực tiếp khi push
- **Obsidian / Typora**: render native
- **Online**: copy block mermaid vào https://mermaid.live
