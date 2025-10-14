import os, json, requests
from datetime import datetime
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///alerts.db")
TV_SECRET = os.environ.get("TV_SECRET", "changeme")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    token = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    direction = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="binance")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
app = Flask(__name__)

def _expo_push(token, title, body):
    requests.post("https://exp.host/--/api/v2/push/send", json={"to": token, "title": title, "body": body})

@app.route("/register_alert", methods=["POST"])
def register_alert():
    d = request.get_json(force=True)
    token, symbol = d.get("token"), d.get("symbol","").upper().strip()
    direction, price = d.get("direction","Above"), float(d.get("price"))
    source = d.get("source","binance")
    if not token or not symbol or direction not in ("Above","Below"):
        return jsonify({"error":"Invalid payload"}), 400
    with Session() as s:
        cnt = s.query(func.count(Alert.id)).filter(Alert.token==token, Alert.active==True).scalar()
        if cnt >= 10: return jsonify({"error":"Max 10 active alerts per device token"}), 400
        a = Alert(token=token, symbol=symbol, direction=direction, price=price, source=source, active=True)
        s.add(a); s.commit()
        return jsonify({"status":"ok","id":a.id})

@app.route("/alerts", methods=["GET"])
def list_alerts():
    token = request.args.get("token","")
    with Session() as s:
        rows = s.query(Alert).filter(Alert.token==token, Alert.active==True).order_by(Alert.created_at.desc()).all()
        return jsonify([{"id":r.id,"symbol":r.symbol,"direction":r.direction,"price":r.price,"source":r.source} for r in rows])

@app.route("/alert/<int:aid>", methods=["DELETE"])
def delete_alert(aid):
    token = request.args.get("token","")
    with Session() as s:
        r = s.query(Alert).filter(Alert.id==aid, Alert.token==token).first()
        if not r: return jsonify({"error":"Not found"}), 404
        r.active=False; s.commit(); return jsonify({"status":"deleted"})

@app.route("/tv_webhook", methods=["POST"])
def tv_webhook():
    if request.args.get("secret","") != TV_SECRET:
        return jsonify({"error":"Unauthorized"}), 401
    d = request.get_json(force=True)
    symbol = str(d.get("symbol","")).upper()
    price = float(d.get("price"))
    n = _evaluate(symbol, price, "tradingview")
    return jsonify({"status":"ok","triggered":n})

@app.route("/_internal_eval", methods=["POST"])
def internal_eval():
    d = request.get_json(force=True)
    return jsonify({"triggered": _evaluate(d["symbol"], float(d["price"]), d.get("source","binance"))})

def _evaluate(symbol, price, source):
    n=0
    with Session() as s:
        for a in s.query(Alert).filter(Alert.active==True, Alert.symbol==symbol, Alert.source==source).all():
            if (a.direction=="Above" and price>=a.price) or (a.direction=="Below" and price<=a.price):
                _expo_push(a.token, f"{symbol} Alert!", f"Price {price} crossed {a.price}")
                a.active=False; s.add(a); n+=1
        s.commit()
    return n

@app.route("/health")
def health(): return jsonify({"status":"ok"})
