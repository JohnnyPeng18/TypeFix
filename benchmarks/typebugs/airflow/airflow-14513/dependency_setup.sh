sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y apt-utils mysql-server libmysqlclient-dev libxml2 libpq-dev libkrb5-dev libsasl2-dev unixodbc-dev libldap2-dev
export SLUGIFY_USES_TEXT_UNIDECODE=yes

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

pip install --upgrade pip
pip install -r ./pyter_requirements.txt
pip install -e .
export PYTHONIOENCODING=utf-8

pip install apache-airflow-providers-sqlite==1.0.1 apache-airflow-providers-ftp==1.0.1 apache-airflow-providers-http==1.1.0 apache-airflow-providers-imap==1.0.1

airflow db init