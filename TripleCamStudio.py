# -*- coding: utf-8 -*-
"""TripleCam Studio V2.0 beta. Place beside Hikrobot MVS sample imports."""
import os, sys, json, time, tempfile, shutil
from datetime import datetime
from ctypes import cast, POINTER
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PyQt5.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QLineEdit,QDoubleSpinBox,QSpinBox,QCheckBox,QFrame,QFileDialog,
    QMessageBox,QDialog,QDialogButtonBox,QTextEdit,QScrollArea,QGroupBox)
from MvCameraControl_class import *
from CameraParams_header import MV_CC_DEVICE_INFO_LIST, MV_CC_DEVICE_INFO
from MvErrorDefine_const import *
from CamOperation_OneClick import CameraOperation
from capture_storage import CAMERA_ROLES, CaptureStorage, camera_directories

HERE=Path(__file__).resolve().parent
CONFIG=HERE/'config.json'

def hx(ret): return '0x%08X' % (ret & 0xffffffff)
def decode(arr):
    b=bytes(arr).split(b'\0',1)[0]
    for enc in ('ascii','gbk','utf-8'):
        try: return b.decode(enc)
        except UnicodeDecodeError: pass
    return b.decode('latin1',errors='replace')

def load_config():
    with open(CONFIG,encoding='utf-8') as f: return json.load(f)
def save_config(c):
    temp=str(CONFIG)+'.tmp'
    with open(temp,'w',encoding='utf-8') as f: json.dump(c,f,ensure_ascii=False,indent=2)
    os.replace(temp,CONFIG)

class ROIView(QLabel):
    changed=pyqtSignal(object)
    def __init__(self):
        super().__init__(); self.setMinimumSize(660,430); self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('background:#101923;border-radius:8px;'); self.image=None; self.roi=None; self.origin=None
    def set_image(self,path,roi):
        self.image=QImage(str(path)); self.roi=QRect(*roi) if roi else QRect(0,0,self.image.width(),self.image.height()); self.update()
    def image_rect(self):
        if self.image is None or self.image.isNull(): return QRect()
        scaled=self.image.size().scaled(self.size(),Qt.KeepAspectRatio)
        return QRect((self.width()-scaled.width())//2,(self.height()-scaled.height())//2,scaled.width(),scaled.height())
    def to_image(self,p):
        r=self.image_rect(); x=max(0,min(self.image.width()-1,round((p.x()-r.x())*self.image.width()/max(1,r.width()))))
        y=max(0,min(self.image.height()-1,round((p.y()-r.y())*self.image.height()/max(1,r.height()))))
        return QPoint(x,y)
    def paintEvent(self,e):
        super().paintEvent(e)
        if self.image is None or self.image.isNull(): return
        p=QPainter(self); r=self.image_rect(); p.drawImage(r,self.image)
        if self.roi:
            x=r.x()+self.roi.x()*r.width()/self.image.width(); y=r.y()+self.roi.y()*r.height()/self.image.height()
            w=self.roi.width()*r.width()/self.image.width(); h=self.roi.height()*r.height()/self.image.height()
            p.fillRect(QRect(round(x),round(y),round(w),round(h)),QColor(25,120,240,45))
            p.setPen(QPen(QColor('#48a7ff'),2)); p.drawRect(QRect(round(x),round(y),round(w),round(h)))
    def mousePressEvent(self,e):
        if self.image and e.button()==Qt.LeftButton: self.origin=self.to_image(e.pos()); self.roi=QRect(self.origin,self.origin); self.update()
    def mouseMoveEvent(self,e):
        if self.origin is not None:
            self.roi=QRect(self.origin,self.to_image(e.pos())).normalized(); self.update()
    def mouseReleaseEvent(self,e):
        if self.origin is not None:
            self.origin=None
            if self.roi.width()>0 and self.roi.height()>0: self.changed.emit([self.roi.x(),self.roi.y(),self.roi.width(),self.roi.height()])

class ROIEditor(QDialog):
    def __init__(self,parent,image_path,roi):
        super().__init__(parent); self.setWindowTitle('ROI Editor | 工程师区域设置'); self.resize(900,680)
        l=QVBoxLayout(self); l.addWidget(QLabel('拖拽鼠标框选保存区域；也可以在下方输入像素坐标。'))
        self.view=ROIView(); self.view.set_image(image_path,roi); l.addWidget(self.view,1)
        row=QHBoxLayout(); self.spins=[]
        for text in ('X','Y','Width','Height'):
            row.addWidget(QLabel(text)); sp=QSpinBox(); sp.setRange(0,100000); row.addWidget(sp); self.spins.append(sp)
        l.addLayout(row)
        self.view.changed.connect(self.update_spins)
        self.update_spins([self.view.roi.x(),self.view.roi.y(),self.view.roi.width(),self.view.roi.height()])
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self.validate); btns.rejected.connect(self.reject); l.addWidget(btns)
    def update_spins(self,vals):
        for s,v in zip(self.spins,vals): s.setValue(v)
    def validate(self):
        x,y,w,h=[s.value() for s in self.spins]; img=self.view.image
        if not w or not h or x+w>img.width() or y+h>img.height():
            QMessageBox.warning(self,'Invalid ROI','ROI must be inside the full image.'); return
        self.result_roi=[x,y,w,h]; self.accept()

class CameraPanel(QFrame):
    def __init__(self,slot,change_cb,roi_cb):
        super().__init__(); self.slot=slot; self.setObjectName('cameraPanel')
        lay=QVBoxLayout(self); top=QHBoxLayout(); self.title=QLabel('Camera %d'%(slot+1)); self.title.setObjectName('panelTitle')
        self.status=QLabel('● Offline'); self.status.setStyleSheet('color:#a0a8b5'); top.addWidget(self.title); top.addStretch(); top.addWidget(self.status); lay.addLayout(top)
        self.screen=QLabel('等待连接 / Preview'); self.screen.setAlignment(Qt.AlignCenter); self.screen.setMinimumSize(280,200)
        self.screen.setStyleSheet('background:#121a27;color:#8794a8;border-radius:8px;'); lay.addWidget(self.screen,1)
        name_row=QHBoxLayout(); name_row.addWidget(QLabel('名称')); self.name=QLineEdit(); name_row.addWidget(self.name); lay.addLayout(name_row)
        exp_row=QHBoxLayout(); exp_row.addWidget(QLabel('曝光 (μs)')); self.exp=QDoubleSpinBox(); self.exp.setRange(1,10000000); self.exp.setDecimals(1); self.exp.setSingleStep(500)
        exp_row.addWidget(self.exp); self.apply=QPushButton('应用曝光'); self.apply.clicked.connect(lambda:change_cb(self.slot)); exp_row.addWidget(self.apply); lay.addLayout(exp_row)
        roi_row=QHBoxLayout(); self.roi_status=QLabel('ROI: Full Frame'); roi_row.addWidget(self.roi_status); roi_row.addStretch()
        self.roi_btn=QPushButton('编辑 ROI'); self.roi_btn.clicked.connect(lambda:roi_cb(self.slot)); roi_row.addWidget(self.roi_btn); lay.addLayout(roi_row)
        self.last=QLabel('尚无采集'); self.last.setObjectName('subtle'); lay.addWidget(self.last)

class Studio(QMainWindow):
    def __init__(self):
        super().__init__(); self.cfg=load_config(); self.devices=None; self.cams=[None]*3; self.ready=False; self.preview=False; self.busy=False; self.pending={}; self.saved={}; self.errors={}; self.frames={}; self.batch=None; self.storage=CaptureStorage()
        self.setWindowTitle('TripleCam Studio | Industrial Capture'); self.resize(1470,900)
        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root); main.setSpacing(14); main.setContentsMargins(22,18,22,18)
        header=QHBoxLayout(); title=QLabel('TripleCam Studio'); title.setObjectName('appTitle'); header.addWidget(title); header.addStretch()
        self.global_status=QLabel('● 未配置'); header.addWidget(self.global_status); main.addLayout(header)
        top=QHBoxLayout(); self.configure=QPushButton('⚙  一键配置'); self.configure.setObjectName('secondaryButton'); self.configure.clicked.connect(self.configure_all); top.addWidget(self.configure)
        self.preview_button=QPushButton('结束预览 / 准备拍照'); self.preview_button.clicked.connect(self.enter_capture_mode); self.preview_button.setEnabled(False); top.addWidget(self.preview_button)
        self.capture=QPushButton('●  一键拍照 · 3 Cameras'); self.capture.setObjectName('primaryButton'); self.capture.setEnabled(False); self.capture.clicked.connect(self.capture_once); top.addWidget(self.capture)
        top.addStretch(); main.addLayout(top)
        grid=QHBoxLayout(); self.panels=[]
        for i in range(3):
            p=CameraPanel(i,self.apply_exposure,self.edit_roi); self.panels.append(p); grid.addWidget(p,1)
            item=self.cfg['cameras'][i]; p.name.setText(item['name']); p.exp.setValue(item['exposure_us']); p.roi_status.setText(self.roi_text(item.get('roi')))
            p.name.editingFinished.connect(lambda slot=i:self.persist_name(slot))
        main.addLayout(grid,5)
        self.save_paths=[]; self.folder_buttons=[]
        for i,directory in enumerate(camera_directories(self.cfg)):
            row=QHBoxLayout(); row.addWidget(QLabel('Camera %d · %s 保存到'%(i+1,CAMERA_ROLES[i])))
            path=QLineEdit(directory); self.save_paths.append(path); row.addWidget(path,1)
            path.editingFinished.connect(lambda slot=i:self.persist_folder(slot))
            browse=QPushButton('选择目录'); browse.clicked.connect(lambda checked=False,slot=i:self.choose_folder(slot))
            self.folder_buttons.append(browse); row.addWidget(browse); main.addLayout(row)
        self.result=QLabel('等待拍照'); main.addWidget(self.result)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(130); main.addWidget(self.log,1)
        self.setStyleSheet('''QMainWindow,QWidget{background:#f3f6fa;color:#253248;font-family:"Microsoft YaHei";font-size:13px}
        QFrame#cameraPanel{background:white;border:1px solid #dce4ef;border-radius:13px}
        QLabel#appTitle{font-size:27px;font-weight:700;color:#172a44} QLabel#panelTitle{font-size:17px;font-weight:700}
        QLabel#subtle{color:#8c98a8} QLineEdit,QDoubleSpinBox,QSpinBox{background:#fff;border:1px solid #cad5e3;border-radius:6px;padding:7px}
        QPushButton{background:#e8edf5;color:#1c3654;border:1px solid #cdd9e7;border-radius:7px;padding:10px 15px;font-weight:600}
        QPushButton:hover{background:#dbe8f9} QPushButton:disabled{color:#9fa9b7;background:#e9ecf0}
        QPushButton#primaryButton{background:#196ce2;color:white;border:none;font-size:16px;padding:14px 24px}
        QPushButton#primaryButton:disabled{background:#b8c9df} QTextEdit{background:#fff;border:1px solid #dce4ef;border-radius:8px}''')
        self.logline('软件已启动。点击「一键配置」连接三台相机。')
    def logline(self,msg): self.log.append(datetime.now().strftime('%H:%M:%S')+'  '+msg)
    def roi_text(self,roi): return 'ROI: %s'%(('Full Frame' if not roi else '%d × %d'%(roi[2],roi[3])))
    def persist_name(self,slot):
        name=self.panels[slot].name.text().strip() or ('Camera %d'%(slot+1)); self.cfg['cameras'][slot]['name']=name; save_config(self.cfg); self.panels[slot].title.setText(name)
    def persist_folder(self,slot):
        if self.busy:return
        directory=self.save_paths[slot].text().strip()
        if not directory:return
        try:
            self.cfg['cameras'][slot]['save_dir']=directory
            save_config(self.cfg)
        except Exception as e: QMessageBox.warning(self,'保存配置失败',str(e))
    def choose_folder(self,slot):
        d=QFileDialog.getExistingDirectory(self,'选择 %s 相机保存目录'%CAMERA_ROLES[slot],self.save_paths[slot].text())
        if d:
            self.save_paths[slot].setText(d); self.persist_folder(slot)
    def enable_folder_controls(self,enabled):
        for control in self.save_paths+self.folder_buttons:control.setEnabled(enabled)
    def enumerate(self):
        lst=MV_CC_DEVICE_INFO_LIST(); layers=(MV_GIGE_DEVICE|MV_USB_DEVICE|MV_GENTL_GIGE_DEVICE|MV_GENTL_CAMERALINK_DEVICE|MV_GENTL_CXP_DEVICE|MV_GENTL_XOF_DEVICE)
        ret=MvCamera.MV_CC_EnumDevicesEx2(layers,lst,'',SortMethod_SerialNumber)
        if ret: raise RuntimeError('枚举失败 '+hx(ret))
        mapping={}
        for i in range(lst.nDeviceNum):
            info=cast(lst.pDeviceInfo[i],POINTER(MV_CC_DEVICE_INFO)).contents
            if info.nTLayerType in (MV_GIGE_DEVICE,MV_GENTL_GIGE_DEVICE): serial=decode(info.SpecialInfo.stGigEInfo.chSerialNumber)
            elif info.nTLayerType==MV_USB_DEVICE: serial=decode(info.SpecialInfo.stUsb3VInfo.chSerialNumber)
            else: continue
            mapping[serial]=i
        return lst,mapping
    def configure_all(self):
        if self.busy:return
        self.configure.setEnabled(False)
        try:
            self.shutdown_cameras(); self.devices,mapping=self.enumerate()
            missing=[x['serial'] for x in self.cfg['cameras'] if x['serial'] not in mapping]
            if missing: raise RuntimeError('未找到指定序列号相机: '+', '.join(missing))
            for i,entry in enumerate(self.cfg['cameras']):
                cam=CameraOperation(MvCamera(),self.devices,mapping[entry['serial']]); self.cams[i]=cam
                self.check(cam.open_device(),'Camera %d open'%(i+1))
                self.check(cam.set_trigger_mode('continuous'),'Camera %d preview mode'%(i+1))
                self.check(cam.set_exposure_time(str(self.panels[i].exp.value())),'Camera %d exposure'%(i+1))
                if entry.get('gain_db') is not None: self.check(cam.set_gain(str(entry['gain_db'])),'Camera %d gain'%(i+1))
                self.check(cam.start_grabbing(i,int(self.panels[i].screen.winId())),'Camera %d start'%(i+1))
                self.panels[i].status.setText('● Online'); self.panels[i].status.setStyleSheet('color:#16865a')
                entry['exposure_us']=self.panels[i].exp.value()
            save_config(self.cfg); self.ready=True; self.preview=True; self.preview_button.setEnabled(True); self.capture.setEnabled(False)
            self.global_status.setText('● 3/3 已连接 · 预览中'); self.logline('三台相机连接成功。正在实时预览；检查 ROI 后点击「结束预览 / 准备拍照」。')
        except Exception as exc:
            self.logline('配置失败: '+str(exc)); QMessageBox.warning(self,'配置失败',str(exc)); self.shutdown_cameras()
        finally: self.configure.setEnabled(True)
    def check(self,ret,label):
        if ret != 0: raise RuntimeError(label+' failed '+hx(ret))
    def enter_capture_mode(self):
        if not self.ready:return
        try:
            for i,cam in enumerate(self.cams):
                self.check(cam.stop_grabbing(),'stop camera %d'%i)
                self.check(cam.set_trigger_mode('triggermode'),'trigger mode camera %d'%i)
                self.check(cam.set_trigger_source('software'),'software source camera %d'%i)
                self.check(cam.start_grabbing(i,int(self.panels[i].screen.winId())),'restart camera %d'%i)
            self.preview=False; self.capture.setEnabled(True); self.preview_button.setText('进入调试预览'); self.preview_button.clicked.disconnect(); self.preview_button.clicked.connect(self.enter_preview)
            self.global_status.setText('● 3/3 就绪 · 软件触发'); self.logline('已进入软件触发模式，可以一键拍照。')
        except Exception as e: self.logline('切换触发模式失败: '+str(e)); QMessageBox.warning(self,'Error',str(e)); self.shutdown_cameras()
    def enter_preview(self):
        if not self.ready or self.busy:return
        try:
            for i,cam in enumerate(self.cams):
                self.check(cam.stop_grabbing(),'stop camera %d'%i)
                self.check(cam.set_trigger_mode('continuous'),'preview camera %d'%i)
                self.check(cam.start_grabbing(i,int(self.panels[i].screen.winId())),'restart camera %d'%i)
            self.preview=True; self.capture.setEnabled(False); self.preview_button.setText('结束预览 / 准备拍照'); self.preview_button.clicked.disconnect(); self.preview_button.clicked.connect(self.enter_capture_mode)
            self.global_status.setText('● 3/3 已连接 · 预览中')
        except Exception as e: QMessageBox.warning(self,'Error',str(e)); self.shutdown_cameras()
    def apply_exposure(self,slot):
        cam=self.cams[slot]; value=self.panels[slot].exp.value()
        if cam is None:
            self.cfg['cameras'][slot]['exposure_us']=value; save_config(self.cfg); self.logline('Camera %d 曝光已保存，连接后生效。'%(slot+1)); return
        if self.busy:return
        ret=cam.set_exposure_time(str(value))
        if ret==0:
            self.cfg['cameras'][slot]['exposure_us']=value; save_config(self.cfg); self.logline('Camera %d 曝光已应用: %.1f μs'%(slot+1,value))
        else: QMessageBox.warning(self,'Exposure failed',hx(ret))
    def snapshot_for_roi(self,slot):
        cam=self.cams[slot]
        if cam is None: raise RuntimeError('请先一键配置相机')
        if not self.preview: raise RuntimeError('请先进入调试预览模式再编辑 ROI')
        path=str(HERE/('_roi_preview_%d.bmp'%slot))
        ret=cam.save_bmp(path)
        if ret!=0 or not os.path.isfile(path): raise RuntimeError('预览截图失败 '+hx(ret))
        return path
    def edit_roi(self,slot):
        try:
            path=self.snapshot_for_roi(slot); dialog=ROIEditor(self,path,self.cfg['cameras'][slot].get('roi'))
            if dialog.exec_()==QDialog.Accepted:
                self.cfg['cameras'][slot]['roi']=dialog.result_roi; save_config(self.cfg)
                self.panels[slot].roi_status.setText(self.roi_text(dialog.result_roi)); self.logline('Camera %d ROI 已保存: %s'%(slot+1,dialog.result_roi))
            os.remove(path)
        except Exception as e: QMessageBox.warning(self,'ROI Editor',str(e))
    def capture_once(self):
        if not self.ready or self.preview or self.busy:return
        directories=[path.text().strip() for path in self.save_paths]
        try:
            # Check all destinations before triggering any camera.
            for entry,directory in zip(self.cfg['cameras'],directories):entry['save_dir']=directory
            save_config(self.cfg)
            self.batch=self.storage.prepare(directories)
        except Exception as e: QMessageBox.warning(self,'保存目录错误',str(e)); return
        self.busy=True; self.capture.setEnabled(False); self.preview_button.setEnabled(False); self.configure.setEnabled(False)
        self.enable_folder_controls(False)
        self.saved={}; self.errors={}; self.pending={}; self.frames={}
        for i,cam in enumerate(self.cams):
            with cam.buf_lock: self.frames[i]=cam.frame_count
        delay=max(0,int(self.cfg.get('pre_trigger_delay_ms',0)))
        self.logline('开始采集 pic_%d（left / mid / right）'%self.batch.number)
        QTimer.singleShot(delay,self.issue_triggers)
    def issue_triggers(self):
        for i,cam in enumerate(self.cams):
            try: ret=cam.trigger_once()
            except Exception as e:self.errors[i]='触发失败 '+str(e); continue
            if ret!=0:self.errors[i]='触发失败 '+hx(ret)
            else:self.pending[i]=cam
        self.started=time.monotonic(); QTimer.singleShot(50,self.poll_frames)
    def poll_frames(self):
        for i,cam in list(self.pending.items()):
            with cam.buf_lock: count=cam.frame_count; size=int(cam.st_frame_info.nFrameLen)
            if count<=self.frames[i] or size<=0:continue
            temp=str(self.batch.temp_dir/('_raw_cam%d.bmp'%(i+1)))
            try: ret=cam.save_bmp(temp,expected_frame_count=count)
            except Exception as e:
                self.pending.pop(i); self.errors[i]='SDK 保存失败 '+str(e); continue
            if ret==-2:continue
            self.pending.pop(i)
            if ret!=0 or not os.path.isfile(temp):self.errors[i]='SDK 保存失败 '+str(ret);continue
            try:
                image=QImage(temp)
                if image.isNull():raise RuntimeError('BMP 解码失败')
                roi=self.cfg['cameras'][i].get('roi')
                if roi:
                    x,y,w,h=roi
                    if x<0 or y<0 or w<=0 or h<=0 or x+w>image.width() or y+h>image.height():raise RuntimeError('ROI 超出图像范围')
                    image=image.copy(x,y,w,h)
                cropped=str(self.batch.temp_dir/('cropped_cam%d.bmp'%(i+1)))
                if not image.save(cropped,'BMP') or os.path.getsize(cropped)==0:raise RuntimeError('裁剪文件写入失败')
                output=self.batch.publish(i,cropped)
                self.saved[i]=output; self.panels[i].last.setText('✓ '+str(image.width())+' × '+str(image.height()))
                self.logline('Camera %d saved: %s'%(i+1,output))
            except Exception as e:self.errors[i]=str(e)
            finally:
                try:os.remove(temp)
                except OSError:pass
        timeout=max(500,int(self.cfg.get('frame_timeout_ms',8000)))/1000
        if self.pending and time.monotonic()-self.started<timeout:
            QTimer.singleShot(60,self.poll_frames);return
        for i in self.pending:self.errors[i]='等待新帧超时'
        self.finish_capture()
    def finish_capture(self):
        ok=len(self.saved); failed=bool(self.errors)
        if self.cfg.get('save_metadata',False):
            try:
                metadata={'batch':self.batch.number,'time':datetime.now().isoformat(),'status':'failed' if failed else 'success','cameras':[]}
                for i,entry in enumerate(self.cfg['cameras']):
                    metadata['cameras'].append({'role':CAMERA_ROLES[i],'serial':entry['serial'],'name':entry['name'],'exposure_us':entry['exposure_us'],'roi':entry.get('roi'),'file':self.saved.get(i),'error':self.errors.get(i)})
                with open(self.batch.roots[0]/('pic_%d_capture.json'%self.batch.number),'x',encoding='utf-8') as f:json.dump(metadata,f,ensure_ascii=False,indent=2)
            except Exception as e:self.logline('采集记录保存失败（照片不受影响）: '+str(e))
        self.result.setText(('✓ 成功 ' if not failed else '⚠ 部分失败 ')+str(ok)+'/3 · pic_%d'%self.batch.number)
        self.logline('本次拍照 pic_%d：成功 %d/3'%(self.batch.number,ok))
        try:self.batch.close()
        except OSError as e:self.logline('临时文件清理失败: '+str(e))
        self.busy=False; self.capture.setEnabled(True); self.preview_button.setEnabled(True); self.configure.setEnabled(True)
        self.enable_folder_controls(True)
        if failed: QMessageBox.warning(self,'本批次采集失败','成功 %d/3\n'%ok+'\n'.join('Camera %d: %s'%(i+1,e) for i,e in self.errors.items()))
    def shutdown_cameras(self):
        self.ready=False; self.preview=False; self.capture.setEnabled(False); self.preview_button.setEnabled(False)
        for i,cam in enumerate(self.cams):
            if cam:
                try:cam.close_device()
                except Exception as e:self.logline('Camera %d close error: %s'%(i+1,e))
            self.cams[i]=None; self.panels[i].status.setText('● Offline'); self.panels[i].status.setStyleSheet('color:#a0a8b5')
        self.global_status.setText('● 未配置')
    def closeEvent(self,event):
        if self.busy: event.ignore(); QMessageBox.information(self,'提示','请等待本次拍照完成'); return
        self.shutdown_cameras(); MvCamera.MV_CC_Finalize(); event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv)
    MvCamera.MV_CC_Initialize()
    win=Studio(); win.show()
    sys.exit(app.exec_())
