import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s[%(levelname)s][%(filename)s:%(lineno)d] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
fh = logging.FileHandler('/data/project/ypeng/typeerror/typefix.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s[%(levelname)s][%(filename)s:%(lineno)d] %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)