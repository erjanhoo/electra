from django.contrib import admin

from .models import BillingProfile, CartItem, Category, Order, OrderItem, Product, ProductReview


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ('name', 'slug', 'updated_at')
	search_fields = ('name', 'slug')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ('name', 'brand', 'category', 'price', 'rating', 'stock', 'is_active', 'is_featured')
	list_filter = ('category', 'brand', 'is_active', 'is_featured')
	search_fields = ('name', 'brand', 'short_description')
	prepopulated_fields = {'slug': ('brand', 'name')}


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'is_card_linked', 'card_brand', 'card_last4', 'wallet_balance', 'total_spent', 'updated_at')
	list_filter = ('is_card_linked', 'card_brand')
	search_fields = ('user__email', 'user__username', 'card_last4')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
	list_display = ('user', 'product', 'quantity', 'updated_at')
	list_filter = ('product__category', 'product__brand')
	search_fields = ('user__email', 'user__username', 'product__name', 'product__brand')


class OrderItemInline(admin.TabularInline):
	model = OrderItem
	extra = 0
	readonly_fields = ('product_name', 'product_brand', 'product_slug', 'unit_price', 'quantity', 'line_total', 'image_url')
	can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	list_display = ('order_number', 'user', 'status', 'delivery_method', 'item_count', 'total_amount', 'placed_at')
	list_filter = ('status', 'delivery_method', 'used_wallet')
	search_fields = ('order_number', 'user__email', 'user__username', 'payment_last4')
	readonly_fields = ('order_number', 'placed_at', 'created_at', 'updated_at')
	inlines = [OrderItemInline]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
	list_display = ('product', 'user', 'rating', 'updated_at')
	list_filter = ('rating', 'product__category', 'product__brand')
	search_fields = ('product__name', 'product__brand', 'user__email', 'user__username', 'title', 'comment')
