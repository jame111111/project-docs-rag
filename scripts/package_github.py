"""按 Git 提交候选清单打包源码，不创建远程仓库、不推送、不包含本地运行资料。"""
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = ['.cache/', '.venv/', 'data/runtime/', 'data/uploads/', 'data/corpus/',
           'frontend/node_modules/', 'frontend/dist/', 'products/vscode/', 'products/wechat/',
           'docs/wechat/', 'evaluation/results/wechat-2026-10-05/',
           'evaluation/results/baseline-2026-10-05/', 'artifacts/']


def main():
    if (ROOT/'.git').exists():
        git = ['git', '-C', str(ROOT)]
    else:
        git = ['git', '--git-dir=' + str(ROOT/'.cache/publish-check.git'), '--work-tree=' + str(ROOT)]
        subprocess.run(git + ['init', '--quiet'], cwd=ROOT, check=True, capture_output=True)
    raw = subprocess.check_output(git + ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    files = sorted(set(raw.decode('utf-8').strip('\0').split('\0')))
    secret = re.compile(rb'(sk-[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{24,}|hf_[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for name in files:
        path = ROOT/name
        if not path.resolve().is_relative_to(ROOT) or not path.is_file():
            raise ValueError('提交清单含目录外文件或已删除文件：' + name)
        if any(name.startswith(prefix) for prefix in BLOCKED) or (path.name.startswith('.env') and path.name != '.env.example'):
            raise ValueError('本地文件出现在提交清单中，请先取消跟踪：' + name)
        if secret.search(path.read_bytes()):
            raise ValueError('发现疑似密钥，请人工检查，未生成压缩包：' + name)
    output = ROOT/'artifacts/project-docs-assistant-github.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT/name, 'project-docs-assistant/' + name)
    print(f'已核对并打包 {len(files)} 个提交候选文件：{output}')


if __name__ == '__main__':
    main()
