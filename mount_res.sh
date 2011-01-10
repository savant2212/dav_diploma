#!/bin/sh

SECRET_FILE=/tmp/webdav.secret
CONF_FILE=/tmp/webdav.conf

login=`zenity --entry \
	--title="Аутентификация" \
	--text="Введите имя пользователя:"`
	      
if [ login = "" ]; then
      	zenity --error  --text="Имя пользователя не введено"
      	exit 1
fi

password=`zenity --entry \
	--title="Аутентификация" \
	--text="Введите пароль:" \
	--hide-text`
	
if [ password = "" ]; then
      	zenity --error  --text="Пароль не введён"
      	exit 1
fi

if [ ! -e $SECRET_FILE ]; then
	touch $SECRET_FILE
fi
 
chmod 600 $SECRET_FILE

echo "$1 $login $password" > $SECRET_FILE

if [ ! -e $CONF_FILE ]; then
	touch $CONF_FILE
fi
 
chmod 600 $CONF_FILE
echo "secrets $SECRET_FILE" > $CONF_FILE

/home/savant/devel/mount.davfs $1 $2 -oconf=$CONF_FILE
RET=$?

if [ "$RET" == "11" ]; then
	zenity --error  --text="Сервер недоступен. Обратитесь к системному администратору."
elif [ "$RET" != 0 ]; then
	zenity --error  --text="Неправильное имя пользователя или пароль"
fi

rm -f $CONF_FILE $SECRET_FILE