import typer

app = typer.Typer()


@app.callback()
def callback():
    pass


@app.command()
def run():
    print("Pipeline Started")


if __name__ == "__main__":
    app()
