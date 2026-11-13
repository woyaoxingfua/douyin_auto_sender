.PHONY: all install dev install-dev clean test format lint typecheck run build

all: install

install:
	@echo "安装生产依赖..."
	pip install -e .

dev: install-dev

install-dev:
	@echo "安装开发依赖..."
	pip install -e .[dev]

clean:
	@echo "清理构建产物..."
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf dist
	rm -rf *.egg-info

test:
	@echo "运行测试..."
	pytest tests/ -v

test-cov:
	@echo "运行测试并生成覆盖率报告..."
	pytest tests/ -v --cov=. --cov-report=term

format:
	@echo "格式化代码..."
	isort .
	black .

lint:
	@echo "代码检查..."
	flake8 .

typecheck:
	@echo "类型检查..."
	mypy .

run:
	@echo "启动应用..."
	python main.py

build:
	@echo "构建应用..."
	pyinstaller --onefile --windowed --name=douyin-auto-sender --icon=app.ico main.py

setup-pre-commit:
	@echo "配置 pre-commit..."
	pre-commit install

check-pre-commit:
	@echo "运行 pre-commit 检查..."
	pre-commit run --all-files
