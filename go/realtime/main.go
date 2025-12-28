package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"

	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

type hub struct {
	clients map[*websocket.Conn]struct{}
	mu      sync.RWMutex
}

func newHub() *hub {
	return &hub{clients: make(map[*websocket.Conn]struct{})}
}

func (h *hub) add(conn *websocket.Conn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.clients[conn] = struct{}{}
}

func (h *hub) remove(conn *websocket.Conn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.clients, conn)
	conn.Close()
}

func (h *hub) broadcast(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.clients {
		if err := c.WriteMessage(websocket.TextMessage, message); err != nil {
			log.Printf("ws write error: %v", err)
			go h.remove(c)
		}
	}
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	redisURL := getenv("REDIS_URL", "redis://localhost:6379/0")
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("invalid REDIS_URL: %v", err)
	}
	rdb := redis.NewClient(opt)
	sub := rdb.Subscribe(ctx, getenv("REDIS_CHANNEL", "realtime:broadcast"))

	h := newHub()

	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("upgrade error: %v", err)
			return
		}
		h.add(conn)
	})

	go func() {
		ch := sub.Channel()
		for msg := range ch {
			h.broadcast([]byte(msg.Payload))
		}
	}()

	addr := getenv("BIND_ADDR", ":8081")
	server := &http.Server{Addr: addr}

	go func() {
		log.Printf("realtime gateway listening on %s", addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("http server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("shutting down realtime gateway")
	server.Close()
	sub.Close()
	rdb.Close()
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
