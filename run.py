from app import create_app

app = create_app()

if __name__ == '__main__':
    # Windows 로컬 실행: debug=True, 브라우저에서 http://localhost:5000 접속
    app.run(host='127.0.0.1', port=5000, debug=True)
