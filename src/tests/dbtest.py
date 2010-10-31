'''
Created on 31.10.2010

@author: savant
'''
import unittest
from sqlalchemy import create_engine
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapper, sessionmaker, relationship
from actions import actions
from sqlalchemy.sql.expression import desc
from Entity import ActionRestrict, User, TreeObject, Content, Group, Base
from base64 import b64decode

class Test(unittest.TestCase):
    Base = declarative_base()

    def setUp(self):
        self.metadata = Base.metadata
        self.engine = create_engine("sqlite:///:memory:", echo=True)
                
        self.Session = sessionmaker(bind=self.engine)
        self.sess = self.Session()
        
        self.metadata.create_all(self.engine)

    def tearDown(self):
        pass


    def testCreateDefaults(self):
        root=User('root', 'root', 'root')            
        self.sess.add(root)
        self.sess.commit()
        self.assertFalse(root.id == 0, "root has 0 id")
        #default tree_object
        root_element=TreeObject("/",TreeObject.TYPE_COLLECTION,None,root.id,0,0,0,'/')
        self.sess.add(root_element)
        self.sess.commit()
        self.assertFalse(root_element.id == 0, "root_element has 0 id")
        
        
        self.sess.add(ActionRestrict(root.id, 1, root_element.id, actions['ALL']))            
        
        grp_base_dir=TreeObject("root_grp",TreeObject.TYPE_COLLECTION,root_element,0,0,0,0,'/root_grp')
        self.sess.add(grp_base_dir)
        self.sess.commit()
        
        self.sess.add(ActionRestrict(root.id, 1, grp_base_dir.id, actions['ALL']))
        #
                    
        grp = Group("root_grp",grp_base_dir)
        
        grp.users.append(root)
        
        sgrp_base_dir=TreeObject("sroot_grp",TreeObject.TYPE_COLLECTION,root_element,0,0,0,0,'/sroot_grp')
        self.sess.add(sgrp_base_dir)
        self.sess.commit()
        
        self.sess.add(ActionRestrict(root.id, 1, sgrp_base_dir.id, actions['ALL']))
        
        sgrp = Group("root_grp",sgrp_base_dir)
        
        sgrp.users.append(root)
        
        grp.subgroups.append(sgrp)
        
        self.sess.add(grp)
        self.sess.commit()
        
        pass
    

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testDbTest']
    unittest.main()