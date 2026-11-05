.PHONY: test api web demo

test:
	cd backend && python3 -m pytest

api:
	cd backend && python3 -m uvicorn kitline.api:app --reload --port 8000

web:
	cd frontend && npm run dev

demo:
	cd backend && python3 -m kitline.demo
