from app.bootstrap import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=app.state.context.settings.host,
        port=app.state.context.settings.port,
        log_level="info",
    )
