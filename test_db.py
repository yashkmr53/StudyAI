import psycopg
conn = psycopg.connect(
    dbname='studyai',
    user='studyai',
    password='jIqNdghWtOWpvfn0VK--fO_p1nhV8dv9qiS3H2EY-54',
    host='db',
    port='5432'
)
print('Connected:', conn.info.user)
conn.close()
