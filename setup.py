from setuptools import setup, find_packages

setup(
    name="game-assist-ai",
    version="2.3.0",
    description="Real-time game assistant with strategy swarm engine — voice, gameplay, internet, and 7-agent AI for walkthrough help",
    author="Game Assist AI",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.29.0",
        "pydantic>=2.7.0",
        "openai>=1.30.0",
        "numpy>=1.26.0",
        "aiohttp>=3.9.0",
        "Pillow>=10.3.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "full": [
            "openai-whisper>=20240930",
            "pyaudio>=0.2.14",
            "mss>=9.0.0",
            "opencv-python>=4.9.0",
            "anthropic>=0.31.0",
            "asyncpraw>=7.7.0",
            "beautifulsoup4>=4.12.0",
            "youtube_transcript_api>=0.6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "game-assist=src.api.server:run",
        ],
    },
)
