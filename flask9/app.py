from threading import Lock
from flask import Flask, render_template, session, request, jsonify, url_for
from flask_socketio import SocketIO, emit, disconnect
import serial
import MySQLdb       
import configparser      
import math
import time

async_mode = None

app = Flask(__name__)

socketio = SocketIO(app, async_mode=async_mode)

#db connecting
config = configparser.ConfigParser()
config.read('config.cfg')
myhost = config.get('mysqlDB', 'host')
myuser = config.get('mysqlDB', 'user')
mypasswd = config.get('mysqlDB', 'passwd')
mydb = config.get('mysqlDB', 'db')
print(myhost)

app.config['SECRET_KEY'] = 'secret!'

thread = None
thread_lock = Lock()

#connect with arduino
ser = serial.Serial("/dev/ttyUSB0")
ser.baudrate = 9600



def read():    
    data = ser.readline()
    return data


def background_thread(args):
    count = 0
    dataCounter = 0 
    dataList = []
    db = MySQLdb.connect(host=myhost,user=myuser,passwd=mypasswd,db=mydb)
    
    print("############ START LOADING ###############")           
    while True:
        if args:
          A = dict(args).get('A')
          btnV = dict(args).get('button_val')
        else:
            btnV = 'stop'
            A = 1        
        socketio.sleep(0.5)
        
        ser.write(bytes(str(A), 'utf-8'))
        time.sleep(0.5)
        if btnV == 'start':
            read_ser = read()
            if read_ser == b"OK\r\n":
                break
            dataDict = {
                "x": time.time(),
                "w": float(read_ser),
            }
            dataList.append(dataDict)
            socketio.emit('my_response', {'data': dataDict, 'count': count}, namespace='/test')
            count += 1
        else:
            print("stopping.....")
            if len(dataList)>0:
                print(str(dataList))
                fuj = str(dataList).replace("'", "\"")
                print(fuj)
                # ************ zapis do suboru ************
                str2 = "\r\n"
                str1 = str(fuj)
                str3 = str1+str2
                fo = open("static/files/regulovanaV.txt","a+")
                fo.write(str3)
                fo.close()
                # ************ zapis do db ***************
                cursor = db.cursor()
                cursor.execute("SELECT MAX(id) FROM hodnota")
                maxid = cursor.fetchone()
                cursor.execute("INSERT INTO hodnota (id, w) VALUES (%s, %s)", (maxid[0]+1, fuj))
                print("affected rows = {}".format(cursor.rowcount))
                db.commit()                
            dataList = []
            dataCounter = 0
    db.close()        
        

@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)

#real time data displaying in three tabs
@app.route('/tabs', methods=['GET', 'POST'])
def tabs():
    return render_template('tabs.html', async_mode=socketio.async_mode)

#show data from database on graph
@app.route('/graph', methods=['GET', 'POST'])
def graph():
    return render_template('graph.html', async_mode=socketio.async_mode)

#show data from file on graph
@app.route('/graph_from_file', methods=['GET', 'POST'])
def graph_from_file():
    return render_template('graph_from_file.html', async_mode=socketio.async_mode)


#get data from files
@app.route('/read/<string:num>')
def readmyfile(num):
    fo = open("static/files/regulovanaV.txt","r")
    rows = fo.readlines()
    return rows[int(num)-1]

#get data from database
@app.route('/dbdata/<string:num>', methods=['GET', 'POST'])
def dbdata(num):
  db = MySQLdb.connect(host=myhost,user=myuser,passwd=mypasswd,db=mydb)
  cursor = db.cursor()
  print(num)
  cursor.execute("SELECT w FROM hodnota WHERE id=%s", num)
  rv = cursor.fetchone()
  return str(rv[0])

@socketio.on('open')
def open_app(message):    
    print(message)


@socketio.on('start_process', namespace='/test')
def start_process(message):
    session['button_val'] = message['value']   

@socketio.on('my_event', namespace='/test')
def test_message(message):    
    session['A'] = message['value']    
    #emit('my_response',
     #    {'data': message['value'], 'count': session['receive_count']})


@socketio.on('disconnect_request', namespace='/test')
def disconnect_request():
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': 'Disconnected!', 'count': session['receive_count']})
    #disconnect()
    socketio.stop()

@socketio.on('connect', namespace='/test')
def test_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(target=background_thread, args=session._get_current_object())
   # emit('my_response', {'data': 'Connected', 'count': 0})


@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected', request.sid)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80, debug=True)
