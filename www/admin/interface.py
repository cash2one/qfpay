# -*- coding: utf-8 -*-
import datetime
from django.db.models import Count, Sum
from django.db import transaction

from common import debug, cache, raw_sql
from www.misc import consts
from www.misc.decorators import cache_required

from www.admin.models import Permission, UserPermission, Shop, Order, UserToChannel
from www.account.interface import UserBase


dict_err = {
    20101: u'已经存在相同名称的活动',
    20201: u'已经存在相同名称的新闻',
    20202: u'没有找到对应的新闻',
}

dict_err.update(consts.G_DICT_ERROR)

class PermissionBase(object):

    """docstring for PermissionBase"""

    def __init__(self):
        pass

    def get_all_permissions(self):
        '''
        获取所有权限
        '''
        return [x for x in Permission.objects.filter(parent__isnull=True)]

    def get_user_permissions(self, user_id):
        '''
        根据用户id 获取此用户所有权限
        '''
        return [x.permission.code for x in UserPermission.objects.select_related('permission').filter(user_id=user_id)]

    def get_all_administrators(self):
        '''
        获取所有管理员
        '''
        user_ids = [x['user_id'] for x in UserPermission.objects.values('user_id').annotate(dcount=Count('user_id'))]

        return [UserBase().get_user_by_id(x) for x in user_ids]

    @transaction.commit_manually
    def save_user_permission(self, user_id, permissions, creator):
        '''
        修改用户权限
        '''

        if not user_id or not permissions or not creator:
            return 99800, dict_err.get(99800)

        try:
            UserPermission.objects.filter(user_id=user_id).delete()

            for x in permissions:
                UserPermission.objects.create(user_id=user_id, permission_id=x, creator=creator)

            transaction.commit()
        except Exception, e:
            print e
            transaction.rollback()
            return 99900, dict_err.get(99900)

        return 0, dict_err.get(0)

    def cancel_admin(self, user_id):
        '''
        取消管理员
        '''

        if not user_id:
            return 99800, dict_err.get(99800)

        UserPermission.objects.filter(user_id=user_id).delete()

        return 0, dict_err.get(0)


class ShopBase(object):

    def __init__(self, channel_id):
        self.channel_id = channel_id

    def get_shop_by_id(self, shop_id):
        try:
            ps = dict(shop_id=shop_id)

            return Shop.objects.get(**ps)
        except Shop.DoesNotExist:
            return ""

    def get_shop_sort(self, start_date, end_date):
        '''
        获取店铺排行
        '''
        condition = " AND a.channel_id = %s " % self.channel_id

        sql = """
            SELECT a.shop_id, a.name, COUNT(a.shop_id), SUM(b.price) AS total
            FROM admin_shop a, admin_order b 
            WHERE %s <= b.order_date AND b.order_date <= %s
            AND a.shop_id = b.shop_id
        """ + condition + """
            GROUP BY a.shop_id
            ORDER BY total DESC
        """

        return raw_sql.exec_sql(sql, [start_date, end_date])

    def get_order_count(self, start_date, end_date, over_ten=False, shop_id=None):
        '''
        按日期 获取商户交易笔数分组
        '''
        condition = " AND channel_id = %s " % self.channel_id

        if over_ten:
            condition += " AND price >= 10 "
        if shop_id:
            condition += " AND shop_id = %s " % shop_id

        sql = """
            SELECT DATE_FORMAT(order_date, "%%Y-%%m-%%d"), COUNT(shop_id)
            FROM admin_order
            WHERE %s <= order_date AND order_date <= %s
        """ + condition + """
            GROUP BY DATE_FORMAT(order_date, "%%Y-%%m-%%d")
        """

        return raw_sql.exec_sql(sql, [start_date, end_date])

    def get_order_price(self, start_date, end_date, over_ten=False, shop_id=None):
        '''
        按日期 获取商户交易金额分组
        '''

        condition = " AND channel_id = %s " % self.channel_id

        if over_ten:
            condition += " AND price >= 10 "
        if shop_id:
            condition += " AND shop_id = %s " % shop_id

        sql = """
            SELECT DATE_FORMAT(order_date, "%%Y-%%m-%%d"), SUM(price)
            FROM admin_order
            WHERE %s <= order_date AND order_date <= %s
        """ + condition + """
            GROUP BY DATE_FORMAT(order_date, "%%Y-%%m-%%d")
        """

        return raw_sql.exec_sql(sql, [start_date, end_date])

    def get_order_list(self, start_date, end_date, price_sort, shop_id):
        '''
        获取商户交易流水
        '''
        objs = Order.objects.filter(
            channel_id=self.channel_id, order_date__range=(start_date, end_date)
        )

        if shop_id:
            objs = objs.filter(shop_id=shop_id)
        if price_sort:
            objs = objs.order_by('-price')

        return objs

    def get_order_total_group_by_shop(self, start_date, end_date):
        '''
        按店铺id 获取商户交易额分组
        '''
        return Order.objects.filter(
            channel_id=self.channel_id, 
            order_date__range=(start_date, end_date)
        ).values('shop_id').annotate(Sum('price'))

    def get_order_rate_group_by_shop(self, start_date, end_date):
        '''
        按商户id 获取收益金额分组
        '''
        condition = " AND channel_id = %s " % self.channel_id

        sql = """
            SELECT shop_id, SUM(price*rate)
            FROM admin_order
            WHERE %s <= order_date AND order_date <= %s
        """ + condition + """
            GROUP BY shop_id
        """

        return raw_sql.exec_sql(sql, [start_date, end_date])

    def get_shops(self):
        return Shop.objects.filter(channel_id=self.channel_id).exclude(owner=u"渠道录入")

    def get_all_shop(self):
        return Shop.objects.filter(channel_id=self.channel_id)

    def get_all_salesman(self):
        '''
        获取所有的业务员
        '''
        return Shop.objects.filter(channel_id=self.channel_id, owner=u"渠道录入")

    def get_active_shops(self, days=3):
        '''
        获取3天内活跃商户id
        '''
        temp_date = datetime.datetime.now() - datetime.timedelta(days=days)

        sql = """
            SELECT shop_id 
            FROM admin_order 
            WHERE order_date > %s AND channel_id = %s
            group by shop_id
        """

        return raw_sql.exec_sql(sql, [temp_date.strftime('%Y-%m-%d') + ' 00:00:00 ', self.channel_id])

    def get_timesharing(self, date, shop_id=None):
        '''
        按小时 获取商户交易金额分组
        '''

        condition = " AND channel_id = %s " % self.channel_id

        if shop_id:
            condition += " AND shop_id = %s " % shop_id

        sql = """
            SELECT DATE_FORMAT(order_date, "%%H"), SUM(price)
            FROM admin_order
            WHERE %s <= order_date AND order_date <= %s
        """ + condition + """
            GROUP BY DATE_FORMAT(order_date, "%%H")
        """

        return raw_sql.exec_sql(sql, [date + " 00:00:00 ", date + " 23:59:59 "])


    def get_timesharing_detail_group_by_shop_id(self, date, hour):
        '''
        按商户 获取某一时间商户交易金额分组
        '''
        condition = " AND channel_id = %s " % self.channel_id

        sql = """
            SELECT shop_id, SUM(price) AS total
            FROM admin_order
            WHERE %s <= order_date AND order_date <= %s
        """ + condition + """
            GROUP BY shop_id
            ORDER BY total DESC
            LIMIT 0, 10
        """

        return raw_sql.exec_sql(sql, [date+' '+hour+':00:00', date+' '+hour+':59:59'])


class UserToChannelBase(object):

    def get_channels_of_user(self, user_id):
        from www.misc.account import ACCOUNTS

        channels = []

        for per in UserToChannel.objects.filter(user_id=user_id):
            channels.append([x for x in ACCOUNTS if x['CHANNEL_ID']==per.channel_id][0])

        return channels










