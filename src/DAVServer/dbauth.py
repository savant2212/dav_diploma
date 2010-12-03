#Copyright (c) 2010 Nikita Nazarenko (god@savant.su)
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Library General Public
#License as published by the Free Software Foundation; either
#version 2 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Library General Public License for more details.
#
#You should have received a copy of the GNU Library General Public
#License along with this library; if not, write to the Free
#Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
#MA 02111-1307, USA
import urlparse
import urllib



from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from myhandler import User, ActionRestrict
from actions import actions
from DAV.WebDAVServer import DAVRequestHandler
import string
from DAV.errors import DAV_Error
from Entity import audit
import time

class DbAuthHandler(DAVRequestHandler):
    
  
    def get_userinfo(self,user,pw,command):
        
        sess = self.IFACE_CLASS.Session()
        print("try to auth")
        #authenticate user
        user = sess.query(User).filter_by(login=user,password=pw).first()
        sess.close()
        
        if user == None:
            return 0
        else:
            self.IFACE_CLASS.setCurrentUser(user)
            return 1
  

    def get_command_allow(self, user, command):        
        #authorize user for action
        if command not in actions:
            raise Exception
        
        uri=urlparse.urljoin(self.get_baseuri(self.IFACE_CLASS), self.path)
        uri=urllib.unquote(uri)
        
        sess = self.IFACE_CLASS.Session()
        
        #get user
        user = sess.query(User).filter_by(login=user).first()
        #get object
        obj = self.IFACE_CLASS.uri2obj(uri)
        #when creating object, find parent
        
        if obj == None:
            if uri[-1] == '/':
                p_path=string.join(self.path.split('/')[:-2],'/')+'/'
            else:
                p_path=string.join(self.path.split('/')[:-1],'/')+'/'
                
            uri=urlparse.urljoin(self.get_baseuri(self.IFACE_CLASS), p_path)
            uri=urllib.unquote(uri)
            obj = self.IFACE_CLASS.uri2obj(uri)
            
            if obj == None:
                raise DAV_Error
            
        
        #check restrict for user
        result = sess.query(ActionRestrict).filter_by(actor_id=user.id, object_id=obj.id).first()
        
        if result != None:
            sess.close()
            
            if result.action & actions[command] != 0 :
                ins = audit.insert().values(user_id=user.id, object_id=obj.id, action_time=time.time(), action = actions[command], result = True)
                sess.connection().execute(ins)
                sess.commit()
                return 1
            else:
                ins = audit.insert().values(user_id=user.id, object_id=obj.id, action_time=time.time(), action = actions[command], result = False)
                sess.connection().execute(ins)
                sess.commit()
                return 0            
        
        actors=[]
        for grp in user.groups :
            actors.append(grp.id)
        
        result = sess.query(ActionRestrict).filter_by(actor_id=actors, object_id=obj.id, actor_type='2')
        
        sess.close()
        rs=0
        if result != None:
            for r in result:
                rs = rs | r.action 
            
            if rs & actions[command] != 0 :
                ins = audit.insert().values(user_id=user.id, object_id=obj.id, action_time=time.time(), action = actions[command], result = True)
                sess.connection().execute(ins)
                sess.commit()
                return 1
            else:
                ins = audit.insert().values(user_id=user.id, object_id=obj.id, action_time='', action = actions[command], result = False)
                sess.connection().execute(ins)
                sess.commit()
                return 0   
        
        return None
        
     
     	