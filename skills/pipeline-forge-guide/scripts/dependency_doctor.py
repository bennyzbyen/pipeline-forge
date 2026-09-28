"""Inspect only dependencies for the requested feature; never install packages."""
import argparse
import importlib.metadata
import importlib.util
import json
import sys

FEATURES = {
    'knowledge': {},
    'excel': {'openpyxl': 'openpyxl'},
    'pdf': {'reportlab': 'reportlab', 'pypdf': 'pypdf', 'pdfplumber': 'pdfplumber', 'PIL': 'Pillow'},
    'codegen-tests': {'pandas': 'pandas', 'numpy': 'numpy', 'loguru': 'loguru', 'pytest': 'pytest'},
}


def inspect(feature):
    packages = []
    for module, distribution in FEATURES[feature].items():
        available = importlib.util.find_spec(module) is not None
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            version = None
        packages.append({'package': distribution, 'available': available, 'version': version})
    return {'status': 'ready' if sys.version_info >= (3, 10) and all(p['available'] for p in packages) else 'missing_dependency',
            'feature': feature, 'python': sys.version.split()[0], 'packages': packages,
            'scope': 'helper execution only; target job runtime and external rendering tools are separate',
            'action': 'Use an available host runtime. Install only dependencies needed by the selected feature when authorized.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feature', choices=sorted(FEATURES), default='knowledge')
    result = inspect(parser.parse_args().feature)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'ready' else 1)
