import os, time, requests
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///alerts.db")
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5000")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Alert(Base):
    __tablename__="alerts"
    id=Column(Integer, primary_key=True)
    token=Column(String, index=True, nullable=False)
    symbol=Column(String, index=True, nullable=False)
    direction=Column(String, nullable=False)
    price=Column(Float, nullable=False)
    source=Column(String, nullable=False, default="binance")
    active=Column(Boolean, default=True)
    created_at=Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

def binance_price(symbol):
    r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])

def symbols_to_check():
    with Session() as s:
        rows = s.query(Alert.symbol).filter(Alert.active==True, Alert.source=="binance").distinct().all()
        return [r[0] for r in rows]

def main():
    print("[worker] 3s loop running")
    while True:
        try:
            for sym in symbols_to_check():
                try:
                    p = binance_price(sym)
                    requests.post(f"{SERVER_URL}/_internal_eval", json={"symbol":sym,"price":p,"source":"binance"}, timeout=10)
                except Exception as e:
                    print("[worker] symbol error:", sym, e)
        except Exception as e:
            print("[worker] loop error:", e)
        time.sleep(3)

if __name__=="__main__":
    main()
